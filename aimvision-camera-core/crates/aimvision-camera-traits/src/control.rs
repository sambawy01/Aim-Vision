//! Camera control trait — the canonical command surface.
//!
//! `CameraControl` is what the app layer talks to. It is exported across
//! UniFFI to Swift / Kotlin (per ADR-0003 §FFI strategy). Every method is
//! `async` and returns [`CameraResult<T>`]; cancellation is propagated via
//! the underlying transport's cancellation token.

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::capabilities::CameraCapabilities;
use crate::error::CameraResult;
use crate::time_source::TimeNs;

/// Capture mode the camera is in. We expose only the modes V1 actually uses;
/// adding panoramic / timelapse later is non-breaking because the enum is
/// `non_exhaustive`.
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[non_exhaustive]
pub enum CaptureMode {
    /// Standard video capture.
    Video,
    /// Webcam (USB-C UVC) — federation tier.
    Webcam,
    /// Photo (single-frame). Reserved for V2.
    Photo,
}

/// Handle returned from `start_recording`. Opaque to the caller — used to
/// reference the recording later (e.g. for `download_file` post-session).
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct RecordingHandle(pub Uuid);

impl RecordingHandle {
    /// Create a fresh handle. The mock camera and CI fixtures use this.
    #[must_use]
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }
}

impl Default for RecordingHandle {
    fn default() -> Self {
        Self::new()
    }
}

/// Identifier for a camera setting. Hero 13 numbers settings; we wrap that
/// behind a typed identifier so future cameras with named settings (Insta360,
/// custom hardware) can implement the same trait.
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SettingId(pub u16);

/// Setting value as a tagged primitive. Settings on Hero 13 are u8 / u16 /
/// strings; we union them here so the API surface is uniform.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum SettingValue {
    /// Unsigned 8-bit value.
    U8(u8),
    /// Unsigned 16-bit value.
    U16(u16),
    /// Unsigned 32-bit value.
    U32(u32),
    /// Boolean.
    Bool(bool),
    /// String — used for SSIDs, preset names.
    String(String),
}

/// Control trait.
///
/// All methods are `async` — Hero 13 HTTP responses take 50–500 ms
/// typically, BLE commands 100–800 ms. The single-in-flight queue
/// (per `docs/camera-integration-spec.md` §5) is layered on top of this
/// trait by `aimvision-camera-state`, not enforced here.
#[async_trait]
pub trait CameraControl: Send + Sync {
    /// Open the control session: BLE pair + Wi-Fi join (or UVC tether).
    /// Returns when the camera is in `ReadyForRecording`. The state machine
    /// in `aimvision-camera-state` is the orchestrator; this trait is the
    /// raw call.
    async fn connect(&self) -> CameraResult<()>;

    /// Tear the session down gracefully. Stops preview, leaves AP, keeps BLE
    /// keepalive alive for a few seconds so a fast reconnect avoids re-pair.
    async fn disconnect(&self) -> CameraResult<()>;

    /// Begin recording in the current mode. Returns a recording handle that
    /// the caller stores for later file retrieval.
    async fn start_recording(&self) -> CameraResult<RecordingHandle>;

    /// Stop recording. The recording is committed to SD card; file is
    /// available via [`CameraMedia::download_file`](crate::CameraMedia::download_file).
    async fn stop_recording(&self) -> CameraResult<()>;

    /// Pause recording. Note: stock Hero 13 firmware does not support
    /// mid-clip pause — implementations emulate via stop + restart and
    /// reconcile via GPMF chapter timestamps post-session
    /// (per `docs/camera-integration-spec.md` §7.4).
    async fn pause(&self) -> CameraResult<()>;

    /// Resume recording after `pause`.
    async fn resume(&self) -> CameraResult<()>;

    /// Insert a hilight tag at the given camera-clock timestamp.
    /// Best-effort; the GPMF write is not acknowledged until recording stops.
    async fn insert_hilight(&self, at: TimeNs) -> CameraResult<()>;

    /// Set a setting by ID.
    async fn set_setting(&self, id: SettingId, value: SettingValue) -> CameraResult<()>;

    /// Read a setting by ID.
    async fn get_setting(&self, id: SettingId) -> CameraResult<SettingValue>;

    /// Return the immutable capability set advertised by this camera.
    /// Callers should query this before calling methods like `insert_hilight`
    /// on cameras that may not support them.
    fn query_capabilities(&self) -> &CameraCapabilities;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn handle_default_is_unique() {
        let a = RecordingHandle::default();
        let b = RecordingHandle::default();
        assert_ne!(a, b);
    }

    #[test]
    fn setting_value_round_trips() {
        let v = SettingValue::String("AIMVISION-AP".into());
        let s = serde_yaml::to_string(&v).expect("yaml");
        let back: SettingValue = serde_yaml::from_str(&s).expect("yaml-back");
        assert_eq!(v, back);
    }
}
