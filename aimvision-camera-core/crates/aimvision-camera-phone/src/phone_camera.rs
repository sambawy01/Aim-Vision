//! `PhoneCamera` — passive `CameraMedia` backend that accepts frames + audio
//! pushed in from a native (Vision Camera worklet) shim.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::sync::Mutex;

use async_trait::async_trait;

use aimvision_camera_traits::{
    AudioChunk, CameraError, CameraMedia, CameraResult, FileId, Frame, MediaSink,
};

/// Snapshot of internal queue depths and drop counters. Read this from the
/// observability layer to detect chronic backpressure ("ML consumer is too
/// slow, frames are being dropped on the floor").
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct PhoneCameraStats {
    /// Number of frames currently buffered (≤ frame_capacity).
    pub queued_frames: usize,
    /// Number of audio chunks currently buffered (≤ audio_capacity).
    pub queued_audio: usize,
    /// Cumulative frames dropped on overflow since construction.
    pub dropped_frames: u64,
    /// Cumulative audio chunks dropped on overflow since construction.
    pub dropped_audio: u64,
}

/// Dev-mode phone camera backend. Cheaply cloneable — internal state is in
/// `Arc<Mutex<...>>`. See module-level docs for the threading model.
#[derive(Clone)]
pub struct PhoneCamera {
    inner: Arc<Inner>,
}

struct Inner {
    id: String,
    frame_capacity: usize,
    audio_capacity: usize,
    frames: Mutex<VecDeque<Frame>>,
    audio: Mutex<VecDeque<AudioChunk>>,
    dropped_frames: AtomicU64,
    dropped_audio: AtomicU64,
}

impl PhoneCamera {
    /// Construct a new phone backend.
    ///
    /// `id` is an opaque identifier (typically `"phone-0"`, or for multi-phone
    /// captures `"phone-0"`, `"phone-1"`, …); it gets stamped into log lines
    /// and surfaces in the dropped-frames metric.
    ///
    /// `frame_capacity` and `audio_capacity` are per-queue ring-buffer sizes.
    /// At 30 fps, a frame_capacity of 64 ≈ 2 s of jitter tolerance, which
    /// matches the slowest realistic ML consumer hop on a phone. Set higher
    /// only if you know the consumer will block for longer.
    ///
    /// # Panics
    ///
    /// Panics if `frame_capacity == 0` or `audio_capacity == 0` — a zero-cap
    /// queue is never what the caller meant, and silently returning `None`
    /// from every poll would mask the configuration error.
    #[must_use]
    pub fn new(id: impl Into<String>, frame_capacity: usize, audio_capacity: usize) -> Self {
        assert!(frame_capacity > 0, "frame_capacity must be > 0");
        assert!(audio_capacity > 0, "audio_capacity must be > 0");
        Self {
            inner: Arc::new(Inner {
                id: id.into(),
                frame_capacity,
                audio_capacity,
                frames: Mutex::new(VecDeque::with_capacity(frame_capacity)),
                audio: Mutex::new(VecDeque::with_capacity(audio_capacity)),
                dropped_frames: AtomicU64::new(0),
                dropped_audio: AtomicU64::new(0),
            }),
        }
    }

    /// Camera identifier (as passed to `new`).
    #[must_use]
    pub fn id(&self) -> &str {
        &self.inner.id
    }

    /// Push a frame from the native worklet shim.
    ///
    /// On overflow the oldest queued frame is dropped (FIFO eviction) and
    /// the `dropped_frames` counter increments. Returns `true` if a frame
    /// was dropped to make room.
    ///
    /// This is *infallible* by design — the worklet thread cannot afford to
    /// handle errors per-frame; a backpressure event is just a metric.
    pub fn push_frame(&self, frame: Frame) -> bool {
        // Lock poisoning would only happen if a previous holder panicked
        // mid-push; we recover by reading through the poisoned guard. Doing
        // so loses any partial state but the buffer is logically the same.
        let mut q = self
            .inner
            .frames
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let evicted = if q.len() >= self.inner.frame_capacity {
            self.inner.dropped_frames.fetch_add(1, Ordering::Relaxed);
            q.pop_front();
            true
        } else {
            false
        };
        q.push_back(frame);
        evicted
    }

    /// Push an audio chunk from the native shim. Same eviction semantics as
    /// [`Self::push_frame`].
    pub fn push_audio_chunk(&self, chunk: AudioChunk) -> bool {
        let mut q = self
            .inner
            .audio
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let evicted = if q.len() >= self.inner.audio_capacity {
            self.inner.dropped_audio.fetch_add(1, Ordering::Relaxed);
            q.pop_front();
            true
        } else {
            false
        };
        q.push_back(chunk);
        evicted
    }

    /// Cumulative count of frames dropped on overflow since construction.
    #[must_use]
    pub fn dropped_frames(&self) -> u64 {
        self.inner.dropped_frames.load(Ordering::Relaxed)
    }

    /// Cumulative count of audio chunks dropped on overflow since construction.
    #[must_use]
    pub fn dropped_audio(&self) -> u64 {
        self.inner.dropped_audio.load(Ordering::Relaxed)
    }

    /// Atomic snapshot of queue depths + drop counters. Cheap; safe to call
    /// from a metrics-scrape thread.
    #[must_use]
    pub fn stats(&self) -> PhoneCameraStats {
        let queued_frames = self
            .inner
            .frames
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .len();
        let queued_audio = self
            .inner
            .audio
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .len();
        PhoneCameraStats {
            queued_frames,
            queued_audio,
            dropped_frames: self.dropped_frames(),
            dropped_audio: self.dropped_audio(),
        }
    }
}

#[async_trait]
impl CameraMedia for PhoneCamera {
    fn poll_preview_frame(&self) -> Option<Frame> {
        self.inner
            .frames
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .pop_front()
    }

    fn poll_audio_chunk(&self) -> Option<AudioChunk> {
        self.inner
            .audio
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
            .pop_front()
    }

    async fn download_file(&self, _file_id: FileId, _sink: &mut dyn MediaSink) -> CameraResult<()> {
        // Phone capture writes MP4s through Vision Camera's `recordVideo` on
        // the RN side; the backend never enumerates files off the device. The
        // session upload path (ADR-0009 slice 2) is the file-transfer route.
        Err(CameraError::Unsupported(
            "phone backend does not enumerate device files",
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use aimvision_camera_traits::FrameFormat;

    fn mk_frame(seq: u64) -> Frame {
        Frame {
            handle_id: seq * 1000,
            format: FrameFormat::Nv12,
            width: 1920,
            height: 1080,
            pts_ns: seq * 33_333_333, // TimeNs = u64; ~30 fps spacing
            monotonic_seq: seq,
        }
    }

    fn mk_audio(start_ns: u64, samples: usize) -> AudioChunk {
        AudioChunk {
            samples: vec![0i16; samples],
            sample_rate_hz: 48_000,
            channels: 1,
            start_ts_ns: start_ns,
        }
    }

    #[test]
    fn new_phone_is_empty() {
        let cam = PhoneCamera::new("phone-0", 4, 4);
        assert_eq!(cam.id(), "phone-0");
        assert!(cam.poll_preview_frame().is_none());
        assert!(cam.poll_audio_chunk().is_none());
        assert_eq!(cam.dropped_frames(), 0);
        assert_eq!(cam.dropped_audio(), 0);
    }

    #[test]
    fn push_and_poll_preserves_fifo_order() {
        let cam = PhoneCamera::new("phone-0", 8, 8);
        for seq in 0..4 {
            assert!(!cam.push_frame(mk_frame(seq)));
        }
        for seq in 0..4 {
            let f = cam.poll_preview_frame().expect("frame should be present");
            assert_eq!(f.monotonic_seq, seq);
        }
        assert!(cam.poll_preview_frame().is_none());
        assert_eq!(cam.dropped_frames(), 0);
    }

    #[test]
    fn overflow_drops_oldest_and_increments_counter() {
        // Capacity 2 with 5 pushes -> 3 evictions of the oldest entries.
        let cam = PhoneCamera::new("phone-0", 2, 2);
        let evictions: Vec<bool> = (0..5).map(|s| cam.push_frame(mk_frame(s))).collect();
        assert_eq!(evictions, vec![false, false, true, true, true]);
        assert_eq!(cam.dropped_frames(), 3);
        // Only the two newest survive (seq 3, 4).
        assert_eq!(cam.poll_preview_frame().unwrap().monotonic_seq, 3);
        assert_eq!(cam.poll_preview_frame().unwrap().monotonic_seq, 4);
        assert!(cam.poll_preview_frame().is_none());
    }

    #[test]
    fn audio_drop_path_is_independent_of_frame_drop_path() {
        let cam = PhoneCamera::new("phone-0", 8, 2);
        // Fill audio past capacity; frames untouched.
        for n in 0..5 {
            cam.push_audio_chunk(mk_audio(n * 10_000_000, 480));
        }
        assert_eq!(cam.dropped_audio(), 3);
        assert_eq!(cam.dropped_frames(), 0);

        // Push frames; audio drops not affected.
        for s in 0..3 {
            cam.push_frame(mk_frame(s));
        }
        assert_eq!(cam.dropped_frames(), 0);
        assert_eq!(cam.dropped_audio(), 3);
    }

    #[test]
    fn stats_snapshot_matches_observed_state() {
        let cam = PhoneCamera::new("phone-0", 4, 4);
        cam.push_frame(mk_frame(0));
        cam.push_frame(mk_frame(1));
        cam.push_audio_chunk(mk_audio(0, 480));

        let s = cam.stats();
        assert_eq!(s.queued_frames, 2);
        assert_eq!(s.queued_audio, 1);
        assert_eq!(s.dropped_frames, 0);
        assert_eq!(s.dropped_audio, 0);

        let _ = cam.poll_preview_frame();
        let s = cam.stats();
        assert_eq!(s.queued_frames, 1);
    }

    #[tokio::test]
    async fn download_file_returns_unsupported() {
        struct NullSink;
        #[async_trait]
        impl MediaSink for NullSink {
            async fn write_chunk(&mut self, _bytes: &[u8]) -> CameraResult<()> {
                Ok(())
            }
            async fn finalize(&mut self) -> CameraResult<()> {
                Ok(())
            }
        }
        let cam = PhoneCamera::new("phone-0", 4, 4);
        let mut sink = NullSink;
        let err = cam
            .download_file(FileId::new_v4(), &mut sink)
            .await
            .unwrap_err();
        assert!(matches!(err, CameraError::Unsupported(_)));
    }

    #[test]
    fn clone_shares_state_for_cross_thread_use() {
        // `PhoneCamera` derives Clone via Arc — pushing on one handle must
        // be observable from the other. This is what lets the worklet
        // thread push while the Rust consumer thread polls.
        let a = PhoneCamera::new("phone-0", 8, 8);
        let b = a.clone();
        a.push_frame(mk_frame(42));
        let polled = b.poll_preview_frame().expect("frame should be visible");
        assert_eq!(polled.monotonic_seq, 42);
    }

    #[test]
    fn concurrent_push_from_many_threads_is_consistent() {
        // Spawn 8 threads, each pushing 100 frames. Then poll the queue
        // and confirm no rows lost beyond the eviction counter.
        let cam = PhoneCamera::new("phone-0", 1024, 1024);
        let threads: Vec<_> = (0..8u64)
            .map(|t| {
                let cam = cam.clone();
                std::thread::spawn(move || {
                    for s in 0..100u64 {
                        cam.push_frame(mk_frame(t * 1000 + s));
                    }
                })
            })
            .collect();
        for t in threads {
            t.join().unwrap();
        }
        let mut polled = 0usize;
        while cam.poll_preview_frame().is_some() {
            polled += 1;
        }
        assert_eq!(polled + (cam.dropped_frames() as usize), 800);
    }
}
