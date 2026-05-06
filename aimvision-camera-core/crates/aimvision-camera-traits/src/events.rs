//! Camera event enum.
//!
//! Events are pushed from the camera to the app — thermal warnings, battery,
//! SD card, link state, file ready. The enum is `non_exhaustive` and includes
//! a [`CameraEvent::Vendor`] escape hatch so vendor-specific telemetry does
//! not require new enum variants in this crate.

use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::time_source::TimeNs;

/// Identifier for a recorded file on the camera SD card.
///
/// We use UUID v7 internally so file IDs are sortable by creation time.
/// The mock camera generates them deterministically from the fixture.
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct FileId(pub Uuid);

impl FileId {
    /// Create a new random UUID-v4 file ID. Used by the mock camera and tests.
    #[must_use]
    pub fn new_v4() -> Self {
        Self(Uuid::new_v4())
    }
}

/// Thermal state reported by the camera (per-camera, polled every 10 s
/// during recording per `docs/camera-integration-spec.md` §11.1).
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ThermalState {
    /// Operating temperature within nominal envelope.
    Nominal,
    /// Mild heat — drop the live-preview FPS ladder one notch.
    Warm,
    /// Hot — drop pose inference to 5 fps; user-visible warning.
    Hot,
    /// Critical — enforce cooldown protocol; the app pauses recording.
    Critical,
}

/// Vendor-specific event payload (sealed escape hatch).
///
/// We deliberately do not use `Box<dyn Any>` here — UniFFI cannot cross
/// arbitrary `Any` types over the FFI boundary, and the Swift / Kotlin sides
/// would have to reinterpret pointers. Instead the `kind` field is a vendor
/// + identifier string and `payload_json` is a serde-serialized opaque blob.
/// See `docs/camera-integration-spec.md` §13.2.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub struct VendorEvent {
    /// Vendor identifier, e.g. `"gopro"`, `"insta360"`, `"aimvision-v3"`.
    pub vendor: String,
    /// Vendor-defined event kind, e.g. `"stitch_quality_drop"`.
    pub kind: String,
    /// JSON-serialized payload. Consumers who care about vendor specifics
    /// downcast via `serde_json::from_str` on the other side.
    pub payload_json: String,
}

/// Camera-emitted event.
///
/// `non_exhaustive` so adding new variants is not a breaking change. Match
/// arms must include a wildcard.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[non_exhaustive]
pub enum CameraEvent {
    /// Thermal warning with new state.
    ThermalWarning(ThermalState),
    /// Camera shut down to protect itself; recording is lost.
    ThermalShutdown,
    /// Battery percent remaining (0..=100).
    BatteryLow(u8),
    /// Battery is critically low; camera will shut down imminently.
    BatteryCritical,
    /// SD card is full; recording cannot continue.
    SdFull,
    /// Recording started successfully.
    RecordingStarted,
    /// Recording stopped (operator action, error, or thermal).
    RecordingStopped,
    /// A file is available for download.
    FileReady(FileId),
    /// A hilight tag was inserted at the given camera-clock timestamp.
    HilightInserted(TimeNs),
    /// Wi-Fi association came up.
    WifiUp,
    /// Wi-Fi association went down.
    WifiDown,
    /// BLE link dropped (per the 90 s recovery rule from
    /// `docs/camera-integration-spec.md` §3.4 we hold the session open).
    BleDisconnected,
    /// Vendor-defined event (see [`VendorEvent`]).
    Vendor(VendorEvent),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn battery_low_carries_percent() {
        let evt = CameraEvent::BatteryLow(15);
        match evt {
            CameraEvent::BatteryLow(pct) => assert_eq!(pct, 15),
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn vendor_event_is_serde_compatible() {
        let evt = CameraEvent::Vendor(VendorEvent {
            vendor: "gopro".into(),
            kind: "stitch_drop".into(),
            payload_json: "{\"q\":0.42}".into(),
        });
        let json = serde_yaml::to_string(&evt).expect("serialise");
        assert!(json.contains("gopro"));
        assert!(json.contains("stitch_drop"));
    }

    #[test]
    fn file_id_v4_unique() {
        let a = FileId::new_v4();
        let b = FileId::new_v4();
        assert_ne!(a, b);
    }
}
