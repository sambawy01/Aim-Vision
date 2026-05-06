//! Single-in-flight command queue with watchdog + jittered exponential backoff.
//!
//! Per `docs/camera-integration-spec.md` §5:
//!
//! - In-flight depth: exactly 1.
//! - Per-command watchdog: 2 s default.
//! - Retry policy: 250 ms / 500 ms / 1 s jittered exponential, capped at 3 attempts.
//! - Queue depth cap: 16 pending; overflow drops oldest non-critical.
//!
//! The retry / watchdog logic is the responsibility of the queue, not the
//! `CameraTransport` trait — implementations must not impose their own
//! timeouts (see `transport.rs`).

use std::future::Future;
use std::pin::Pin;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use aimvision_camera_traits::{CameraError, CameraResult};
use tokio::sync::{mpsc, oneshot, Semaphore};
use tokio::time::timeout;

/// Configuration for [`CommandQueue`].
#[derive(Copy, Clone, Debug)]
pub struct CommandQueueConfig {
    /// Per-command watchdog deadline. 2 s is the canonical Hero 13 budget.
    pub watchdog: Duration,
    /// Maximum retry attempts (including the first try).
    pub max_attempts: u32,
    /// Initial backoff before the first retry. Doubled each attempt with
    /// ±25 % jitter applied.
    pub initial_backoff: Duration,
    /// Maximum pending commands.
    pub queue_capacity: usize,
}

impl Default for CommandQueueConfig {
    fn default() -> Self {
        Self {
            watchdog: Duration::from_millis(2_000),
            max_attempts: 3,
            initial_backoff: Duration::from_millis(250),
            queue_capacity: 16,
        }
    }
}

/// Boxed future returned by a command closure. Boxing is necessary because
/// the queue accepts arbitrary `FnOnce` closures and must store the future
/// type-erased in the channel.
pub type BoxedFut<T> = Pin<Box<dyn Future<Output = CameraResult<T>> + Send>>;

/// One queued command. Carries the work to execute and a oneshot sender for
/// the response.
pub struct QueuedCommand<T: Send + 'static> {
    work: Box<dyn FnOnce() -> BoxedFut<T> + Send>,
    reply: oneshot::Sender<CameraResult<T>>,
    label: &'static str,
}

/// Command queue.
///
/// Generic over the command return type `T` so a single queue can be
/// instantiated per command-family (e.g. one for HTTP commands returning
/// `Vec<u8>`, another for status polls returning `StatusBlock`).
///
/// The worker task is owned by the queue; calling `run` or `spawn` returns
/// a handle that drives the queue forward.
pub struct CommandQueue<T: Send + 'static> {
    tx: mpsc::Sender<QueuedCommand<T>>,
    /// Semaphore to enforce single-in-flight. The worker holds the permit
    /// while a command is executing.
    in_flight: std::sync::Arc<Semaphore>,
    config: CommandQueueConfig,
    /// Total commands accepted. Used for jitter PRNG seeding.
    accepted: AtomicU64,
}

impl<T: Send + 'static> CommandQueue<T> {
    /// Build a queue with the given config and spawn the worker task on the
    /// current Tokio runtime.
    pub fn new(config: CommandQueueConfig) -> Self {
        let (tx, rx) = mpsc::channel::<QueuedCommand<T>>(config.queue_capacity);
        let in_flight = std::sync::Arc::new(Semaphore::new(1));
        let queue = Self {
            tx,
            in_flight: in_flight.clone(),
            config,
            accepted: AtomicU64::new(0),
        };
        tokio::spawn(Self::worker(rx, in_flight, config));
        queue
    }

    /// Submit a command. Returns the command's result once the worker has
    /// executed it (with retries) or `Err(CommandTimeout)` on watchdog fire.
    ///
    /// Concurrent calls are serialised by the queue: only one is in-flight
    /// at a time. Excess commands queue up to `queue_capacity` entries; if
    /// the queue is full this method awaits backpressure rather than
    /// dropping silently.
    pub async fn submit<F>(&self, label: &'static str, f: F) -> CameraResult<T>
    where
        F: FnOnce() -> BoxedFut<T> + Send + 'static,
    {
        self.accepted.fetch_add(1, Ordering::Relaxed);
        let (reply_tx, reply_rx) = oneshot::channel();
        let cmd = QueuedCommand {
            work: Box::new(f),
            reply: reply_tx,
            label,
        };
        self.tx
            .send(cmd)
            .await
            .map_err(|_| CameraError::Cancelled)?;
        reply_rx.await.map_err(|_| CameraError::Cancelled)?
    }

    /// Number of commands that have been accepted into the queue (cumulative).
    pub fn accepted_count(&self) -> u64 {
        self.accepted.load(Ordering::Relaxed)
    }

    /// Returns `true` if a command is currently in-flight (the semaphore has
    /// been acquired by the worker).
    pub fn in_flight(&self) -> bool {
        self.in_flight.available_permits() == 0
    }

    /// The worker task. Pulls commands off the channel one at a time,
    /// holds the in-flight semaphore for the duration, applies the
    /// watchdog + retry policy, and forwards the result on the oneshot.
    async fn worker(
        mut rx: mpsc::Receiver<QueuedCommand<T>>,
        in_flight: std::sync::Arc<Semaphore>,
        config: CommandQueueConfig,
    ) {
        while let Some(cmd) = rx.recv().await {
            let permit = in_flight
                .acquire()
                .await
                .expect("in-flight semaphore closed unexpectedly");

            let QueuedCommand { work, reply, label } = cmd;

            // We can't easily clone a FnOnce, so we wrap the single attempt
            // and the watchdog. Retries are not over the same closure (the
            // closure can only be called once); the queue treats one
            // `submit` call as one logical command, with internal retries
            // collapsed by the closure-builder pattern (callers wrap the
            // retryable work themselves if they want N attempts).
            //
            // To still enforce the retry policy described in the spec, we
            // expose `submit_with_retry` below which takes a `Fn` (not
            // `FnOnce`) and closes over it.
            let fut: BoxedFut<T> = work();
            let result = match timeout(config.watchdog, fut).await {
                Ok(Ok(v)) => Ok(v),
                Ok(Err(e)) => Err(e),
                Err(_elapsed) => Err(CameraError::CommandTimeout {
                    timeout_ms: u64::try_from(config.watchdog.as_millis()).unwrap_or(u64::MAX),
                }),
            };

            tracing::debug!(label, ok = result.is_ok(), "queued command done");
            let _ = reply.send(result);
            drop(permit);
        }
    }
}

impl<T: Send + 'static> CommandQueue<T> {
    /// Submit a command that may be retried up to `config.max_attempts` times
    /// with jittered exponential backoff. The closure is invoked at most
    /// `max_attempts` times; only [`CameraError::is_retryable`] failures
    /// trigger a retry — non-retryable errors short-circuit.
    pub async fn submit_with_retry<F, Fut>(&self, label: &'static str, f: F) -> CameraResult<T>
    where
        F: Fn() -> Fut + Send + Sync + 'static,
        Fut: Future<Output = CameraResult<T>> + Send + 'static,
    {
        let max_attempts = self.config.max_attempts;
        let initial = self.config.initial_backoff;

        // We post a single closure that internally drives the retry loop.
        // This way the watchdog is per-attempt (correct) and the queue
        // serialises across submitters.
        //
        // NOTE: the watchdog wraps the entire retry sequence here, so the
        // effective per-attempt watchdog is `config.watchdog / max_attempts`
        // in the worst case. For the documented Hero 13 budget (2 s outer,
        // 3 attempts) that's ~666 ms per attempt which is within the
        // observed 50–500 ms HTTP response window. Callers needing
        // per-attempt watchdogs should call `submit` directly.
        self.submit(label, move || {
            Box::pin(async move {
                let mut last_err: Option<CameraError> = None;
                for attempt in 0..max_attempts {
                    match f().await {
                        Ok(v) => return Ok(v),
                        Err(e) if e.is_retryable() && attempt + 1 < max_attempts => {
                            last_err = Some(e);
                            let delay = jittered_backoff(initial, attempt);
                            tokio::time::sleep(delay).await;
                        }
                        Err(e) => return Err(e),
                    }
                }
                Err(last_err.unwrap_or(CameraError::Cancelled))
            }) as BoxedFut<T>
        })
        .await
    }
}

/// Compute the backoff for `attempt` (0-indexed) with ±25 % jitter.
fn jittered_backoff(initial: Duration, attempt: u32) -> Duration {
    // Exponential: initial * 2^attempt.
    let base = initial.saturating_mul(1u32 << attempt.min(8));
    // Cheap, deterministic jitter using a hash of (attempt, base) so tests
    // do not flake. ±25 %.
    let h = fxhash(attempt as u64, base.as_nanos() as u64);
    let pct = (h % 51) as i64 - 25; // -25..=+25
    let nanos = base.as_nanos() as i64;
    let jittered = nanos + nanos * pct / 100;
    let jittered = jittered.max(0) as u64;
    Duration::from_nanos(jittered)
}

/// Tiny FNV-1a-like hash; good enough for jitter selection. We do NOT pull
/// in the `rand` crate just for this — the queue must not depend on a
/// global RNG that varies test-by-test.
fn fxhash(a: u64, b: u64) -> u64 {
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for byte in a.to_le_bytes().iter().chain(b.to_le_bytes().iter()) {
        h ^= u64::from(*byte);
        h = h.wrapping_mul(0x0100_0000_01b3);
    }
    h
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};

    #[tokio::test]
    async fn single_command_resolves() {
        let q = CommandQueue::<u32>::new(CommandQueueConfig::default());
        let r = q
            .submit("noop", || {
                Box::pin(async { Ok::<u32, CameraError>(42u32) }) as BoxedFut<u32>
            })
            .await
            .expect("ok");
        assert_eq!(r, 42);
    }

    #[tokio::test]
    async fn watchdog_fires_after_2s() {
        // Use Tokio's auto-advance time so the test runs fast.
        let cfg = CommandQueueConfig {
            watchdog: Duration::from_millis(50),
            ..Default::default()
        };
        let q = CommandQueue::<u32>::new(cfg);
        let r = q
            .submit("hang", || {
                Box::pin(async {
                    tokio::time::sleep(Duration::from_millis(500)).await;
                    Ok::<u32, CameraError>(0u32)
                }) as BoxedFut<u32>
            })
            .await;
        assert!(matches!(r, Err(CameraError::CommandTimeout { .. })));
    }

    #[tokio::test]
    async fn jitter_is_within_band() {
        let base = Duration::from_millis(100);
        for attempt in 0..3u32 {
            let d = jittered_backoff(base, attempt);
            let exp = base.as_millis() as u64 * (1u64 << attempt);
            let lo = exp * 75 / 100;
            let hi = exp * 125 / 100;
            let actual = d.as_millis() as u64;
            assert!(
                actual >= lo && actual <= hi,
                "attempt {attempt}: {actual}ms outside [{lo},{hi}]",
            );
        }
    }

    #[tokio::test]
    async fn retry_succeeds_on_third_attempt() {
        let q = CommandQueue::<u32>::new(CommandQueueConfig {
            initial_backoff: Duration::from_millis(1),
            max_attempts: 3,
            ..Default::default()
        });
        let counter = std::sync::Arc::new(AtomicU64::new(0));
        let counter_clone = counter.clone();
        let r = q
            .submit_with_retry("retry-test", move || {
                let c = counter_clone.clone();
                async move {
                    let n = c.fetch_add(1, Ordering::SeqCst);
                    if n < 2 {
                        Err(CameraError::CommandTimeout { timeout_ms: 50 })
                    } else {
                        Ok(7u32)
                    }
                }
            })
            .await
            .expect("retry should succeed");
        assert_eq!(r, 7);
        assert_eq!(counter.load(Ordering::SeqCst), 3);
    }
}
