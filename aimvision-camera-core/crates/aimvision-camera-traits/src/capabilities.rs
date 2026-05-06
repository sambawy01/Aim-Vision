//! Camera capability surface.
//!
//! Implementations build a `CameraCapabilities` once at connect time. The
//! app layer queries `caps.hilight` rather than calling `insert_hilight()`
//! and getting `Err(Unsupported)`. This is the "capabilities are queried,
//! not discovered through errors" rule from ADR-0003 §Consequences.

use serde::{Deserialize, Serialize};

/// Frame resolution as `(width, height)` in pixels.
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Resolution {
    /// Pixel width.
    pub width: u32,
    /// Pixel height.
    pub height: u32,
}

impl Resolution {
    /// Construct a [`Resolution`] from `(width, height)`.
    #[must_use]
    pub const fn new(width: u32, height: u32) -> Self {
        Self { width, height }
    }
}

/// Multi-camera time-sync protocol available on a given implementation.
///
/// Hero 13 stock supports neither and falls back to audio-xcorr-only sync
/// (per `docs/multi-camera-sync-spec.md` §3.5 — degraded mode). Hero 13 with
/// Labs firmware exposes `MSync`. Federation V3 hardware will expose `Genlock`.
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum MultiCamSyncProtocol {
    /// Open GoPro Labs `!MSYNC` BLE-broadcast clock anchor.
    MSync,
    /// Hardware genlock (V3 custom hardware).
    Genlock,
    /// Audio-cross-correlation only — no coarse clock anchor available.
    AudioOnly,
}

/// Static, immutable capability description published by an implementation
/// at connect time.
///
/// `non_exhaustive` so adding fields is not a breaking change to downstream
/// crates that match on it.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[non_exhaustive]
pub struct CameraCapabilities {
    /// Whether the camera can stream a live preview at all (UDP MPEG-TS,
    /// USB UVC, etc.). `false` for write-only mock cameras and some legacy SKUs.
    pub live_preview: bool,
    /// Whether `CameraControl::insert_hilight` is honoured.
    pub hilight: bool,
    /// Whether the camera exposes any external trigger path (BLE shutter,
    /// USB-C HID). Hero 13 in V1 has only BLE shutter (~80–150 ms latency).
    pub external_trigger: bool,
    /// Whether the camera can be tethered as a USB-C UVC webcam.
    pub uvc: bool,
    /// Multi-camera sync protocol available, or `None` if single-camera only.
    pub multi_camera_sync: Option<MultiCamSyncProtocol>,
    /// Whether thermal telemetry events are emitted.
    pub thermal_telemetry: bool,
    /// Whether GPMF IMU is available post-download.
    pub imu_gpmf: bool,
    /// Whether dual-band Wi-Fi AP control is exposed (Hero 13+).
    pub dual_band_ap: bool,
    /// Whether raw PCM audio is available (UVC tether path); when `false`
    /// the audio path goes through AAC with the 20–40 ms encoder lookahead.
    pub raw_pcm_audio: bool,
    /// Mono PCM channels available (1 = mono, 2 = stereo, 3 = TDOA mic array).
    pub audio_channels: u8,
    /// Audio sample rate (Hz); 48000 on Hero 13.
    pub audio_sample_rate_hz: u32,
    /// Audio bit depth; 16 on Hero 13.
    pub audio_bit_depth: u8,
    /// Maximum live capture resolution.
    pub max_resolution: Resolution,
}

impl CameraCapabilities {
    /// Convenience constructor for the canonical Hero 13 stock-firmware
    /// capability set. Federation tier with Labs firmware overrides
    /// `multi_camera_sync` to `Some(MSync)` after probing on connect.
    #[must_use]
    pub fn hero13_stock() -> Self {
        Self {
            live_preview: true,
            hilight: true,
            external_trigger: true,
            uvc: true,
            multi_camera_sync: Some(MultiCamSyncProtocol::AudioOnly),
            thermal_telemetry: true,
            imu_gpmf: true,
            dual_band_ap: true,
            raw_pcm_audio: false,
            audio_channels: 1,
            audio_sample_rate_hz: 48_000,
            audio_bit_depth: 16,
            max_resolution: Resolution::new(3840, 2160),
        }
    }

    /// Mock camera capabilities — everything available, fixture-driven.
    /// Tests need the full surface to exercise every code path.
    #[must_use]
    pub fn mock() -> Self {
        Self {
            live_preview: true,
            hilight: true,
            external_trigger: true,
            uvc: true,
            multi_camera_sync: Some(MultiCamSyncProtocol::MSync),
            thermal_telemetry: true,
            imu_gpmf: true,
            dual_band_ap: true,
            raw_pcm_audio: true,
            audio_channels: 1,
            audio_sample_rate_hz: 48_000,
            audio_bit_depth: 16,
            max_resolution: Resolution::new(1920, 1080),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hero13_stock_has_audio_only_sync() {
        let caps = CameraCapabilities::hero13_stock();
        assert_eq!(caps.multi_camera_sync, Some(MultiCamSyncProtocol::AudioOnly));
        assert_eq!(caps.audio_sample_rate_hz, 48_000);
        assert_eq!(caps.max_resolution, Resolution::new(3840, 2160));
    }

    #[test]
    fn mock_advertises_msync() {
        let caps = CameraCapabilities::mock();
        assert_eq!(caps.multi_camera_sync, Some(MultiCamSyncProtocol::MSync));
    }
}
