//! Media plane traits.
//!
//! Per ADR-0003 the media plane crosses the FFI boundary via hand-written
//! `extern "C"`, NOT via UniFFI. This trait is still useful inside the Rust
//! workspace for unit-testing and mock playback; the iOS / Android shim
//! crate is what re-exposes a subset of this surface as a C ABI.
//!
//! Frame handles are described as opaque platform IDs (IOSurface ID on iOS,
//! AHardwareBuffer pointer on Android) — the Rust core never touches pixel
//! bytes for live preview. Audio PCM, however, is owned by the Rust core
//! because shot detection runs on it.

use async_trait::async_trait;
use serde::{Deserialize, Serialize};

use crate::error::CameraResult;
use crate::events::FileId;
use crate::time_source::TimeNs;

/// Format of a [`Frame`] handle. The Rust core does not interpret the bytes;
/// the platform shim layer wraps the handle as a `CVPixelBuffer` /
/// `HardwareBuffer`.
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum FrameFormat {
    /// NV12 (Y planar + UV interleaved). Default from VideoToolbox / MediaCodec.
    Nv12,
    /// I420 / YUV 4:2:0 planar. Used by some software paths.
    I420,
    /// RGBA8 — only in synthetic / mock paths.
    Rgba8,
}

/// Single decoded preview frame.
///
/// `handle_id` is opaque; on iOS it's a `uint32` IOSurface ID, on Android it's
/// the lower 32 bits of an `AHardwareBuffer*`. The Rust core never copies
/// pixels — it only ferries the handle and the timestamp.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Frame {
    /// Opaque platform handle (IOSurface ID / AHardwareBuffer pointer low bits).
    pub handle_id: u64,
    /// Frame format hint.
    pub format: FrameFormat,
    /// Frame width in pixels.
    pub width: u32,
    /// Frame height in pixels.
    pub height: u32,
    /// Camera-clock timestamp in nanoseconds. PTS-derived per
    /// `docs/camera-integration-spec.md` §6.2.
    pub pts_ns: TimeNs,
    /// Per-camera monotonic counter; the canonical frame ID is
    /// `(camera_id, monotonic_seq)` because PTS wraps every ~26 hours.
    pub monotonic_seq: u64,
}

/// One audio chunk of PCM samples.
///
/// Hero 13 default: 48 kHz mono signed 16-bit PCM. Federation USB-C UVC path
/// delivers the same format. We do not decode AAC in this crate — the audio
/// chunk is raw PCM by contract.
#[derive(Clone, Debug, PartialEq)]
pub struct AudioChunk {
    /// Interleaved PCM samples. Length is `samples_per_channel * channels`.
    pub samples: Vec<i16>,
    /// Sample rate in Hz (e.g. 48000).
    pub sample_rate_hz: u32,
    /// Channel count (1 = mono, 2 = stereo, 3 = TDOA mic array).
    pub channels: u8,
    /// Camera-clock timestamp of the first sample, in nanoseconds.
    pub start_ts_ns: TimeNs,
}

impl AudioChunk {
    /// Number of samples per channel in this chunk.
    #[must_use]
    pub fn samples_per_channel(&self) -> usize {
        if self.channels == 0 {
            return 0;
        }
        self.samples.len() / usize::from(self.channels)
    }

    /// Duration of this chunk in nanoseconds.
    #[must_use]
    pub fn duration_ns(&self) -> u64 {
        let n = self.samples_per_channel() as u64;
        if self.sample_rate_hz == 0 {
            return 0;
        }
        n * 1_000_000_000 / u64::from(self.sample_rate_hz)
    }
}

/// Sink for `download_file`. The trait is generic over async writes via a
/// dyn-compatible byte sink.
#[async_trait]
pub trait MediaSink: Send {
    /// Write a chunk of bytes to the sink. Implementations must be async-safe
    /// and may flush opportunistically.
    async fn write_chunk(&mut self, bytes: &[u8]) -> CameraResult<()>;
    /// Finalize the sink. Called once after the last `write_chunk`.
    async fn finalize(&mut self) -> CameraResult<()>;
}

/// Camera media plane.
///
/// `poll_*` returns `Option<_>` (rather than blocking) because the media
/// pipeline runs in a tight inner loop and synchronous polling is what the
/// platform compositor expects. Implementations buffer internally and return
/// `None` when nothing is available.
#[async_trait]
pub trait CameraMedia: Send + Sync {
    /// Pop the oldest available preview frame, or `None` if the buffer is empty.
    fn poll_preview_frame(&self) -> Option<Frame>;

    /// Pop the oldest available audio chunk, or `None` if the buffer is empty.
    fn poll_audio_chunk(&self) -> Option<AudioChunk>;

    /// Download a file by ID into the given sink. The sink is finalized on
    /// success and dropped (without finalize) on error so the caller can
    /// resume via HTTP Range; partial files are not silently kept.
    async fn download_file(&self, file_id: FileId, sink: &mut dyn MediaSink) -> CameraResult<()>;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn audio_chunk_duration_math() {
        let chunk = AudioChunk {
            samples: vec![0i16; 480], // 480 samples mono @ 48 kHz = 10 ms
            sample_rate_hz: 48_000,
            channels: 1,
            start_ts_ns: 0,
        };
        assert_eq!(chunk.samples_per_channel(), 480);
        assert_eq!(chunk.duration_ns(), 10_000_000); // 10 ms
    }

    #[test]
    fn audio_chunk_handles_zero_channels_safely() {
        let chunk = AudioChunk {
            samples: vec![],
            sample_rate_hz: 48_000,
            channels: 0,
            start_ts_ns: 0,
        };
        assert_eq!(chunk.samples_per_channel(), 0);
        assert_eq!(chunk.duration_ns(), 0);
    }
}
