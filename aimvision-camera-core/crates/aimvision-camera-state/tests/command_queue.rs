//! Command queue tests.
//!
//! Per `docs/camera-integration-spec.md` §5: spawn 5 concurrent `submit`
//! calls and assert serial execution + watchdog fires after 2 s.

use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;

use aimvision_camera_state::{BoxedFut, CommandQueue, CommandQueueConfig};
use aimvision_camera_traits::CameraError;

#[tokio::test]
async fn five_concurrent_submits_serialise() {
    let q: Arc<CommandQueue<u32>> = Arc::new(CommandQueue::new(CommandQueueConfig::default()));
    let in_flight = Arc::new(AtomicU32::new(0));
    let max_observed = Arc::new(AtomicU32::new(0));

    let mut handles = Vec::new();
    for i in 0..5u32 {
        let q = q.clone();
        let in_flight = in_flight.clone();
        let max_observed = max_observed.clone();
        let h = tokio::spawn(async move {
            q.submit("concurrent", move || {
                let in_flight = in_flight.clone();
                let max_observed = max_observed.clone();
                Box::pin(async move {
                    let n = in_flight.fetch_add(1, Ordering::SeqCst) + 1;
                    let prev = max_observed.load(Ordering::SeqCst);
                    if n > prev {
                        max_observed.store(n, Ordering::SeqCst);
                    }
                    tokio::time::sleep(Duration::from_millis(50)).await;
                    in_flight.fetch_sub(1, Ordering::SeqCst);
                    Ok::<u32, CameraError>(i)
                }) as BoxedFut<u32>
            })
            .await
        });
        handles.push(h);
    }

    let mut returned = Vec::new();
    for h in handles {
        let r = h.await.expect("task join").expect("submit ok");
        returned.push(r);
    }

    // All five commands must have completed.
    assert_eq!(returned.len(), 5);
    // Crucial: at no point did more than one command run in parallel.
    assert_eq!(
        max_observed.load(Ordering::SeqCst),
        1,
        "expected single in-flight; observed up to {} concurrent",
        max_observed.load(Ordering::SeqCst)
    );
    // Five accepted into the queue.
    assert_eq!(q.accepted_count(), 5);
}

#[tokio::test]
async fn watchdog_fires_for_hung_command() {
    let cfg = CommandQueueConfig {
        watchdog: Duration::from_millis(100),
        ..Default::default()
    };
    let q = CommandQueue::<u32>::new(cfg);
    let r = q
        .submit("hang", || {
            Box::pin(async {
                tokio::time::sleep(Duration::from_secs(5)).await;
                Ok::<u32, CameraError>(0)
            }) as BoxedFut<u32>
        })
        .await;
    assert!(matches!(r, Err(CameraError::CommandTimeout { timeout_ms }) if timeout_ms == 100));
}

#[tokio::test(start_paused = true)]
async fn watchdog_fires_at_two_seconds_default() {
    // The canonical Hero 13 budget is 2 s. Verify the default config
    // produces a 2-second timeout. `start_paused = true` runs this on a
    // current-thread runtime with the clock paused so virtual-time
    // `advance` works deterministically.
    let q = CommandQueue::<u32>::new(CommandQueueConfig::default());
    let handle = tokio::spawn(async move {
        q.submit("hang", || {
            Box::pin(async {
                tokio::time::sleep(Duration::from_secs(60)).await;
                Ok::<u32, CameraError>(0)
            }) as BoxedFut<u32>
        })
        .await
    });
    // Advance just past the 2 s watchdog.
    tokio::time::advance(Duration::from_millis(2_001)).await;
    let r = handle.await.expect("task join");
    assert!(matches!(r, Err(CameraError::CommandTimeout { timeout_ms }) if timeout_ms == 2000));
}

#[tokio::test]
async fn nonretryable_error_short_circuits_retries() {
    let q = CommandQueue::<u32>::new(CommandQueueConfig {
        max_attempts: 5,
        initial_backoff: Duration::from_millis(1),
        ..Default::default()
    });
    let attempts = Arc::new(AtomicU32::new(0));
    let attempts_clone = attempts.clone();
    let r = q
        .submit_with_retry("noretry", move || {
            let a = attempts_clone.clone();
            async move {
                a.fetch_add(1, Ordering::SeqCst);
                // Bonded is non-retryable per CameraError::is_retryable.
                Err::<u32, CameraError>(CameraError::Bonded)
            }
        })
        .await;
    assert!(matches!(r, Err(CameraError::Bonded)));
    assert_eq!(
        attempts.load(Ordering::SeqCst),
        1,
        "non-retryable error should not be retried"
    );
}
