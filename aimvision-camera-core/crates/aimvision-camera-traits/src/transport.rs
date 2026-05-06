//! Transport trait — the BLE / Wi-Fi / USB-C link layer.
//!
//! Transports are negotiated once per session and are sticky. Silent fallback
//! mid-string would corrupt timing analytics (see
//! `docs/camera-integration-spec.md` §2).

use async_trait::async_trait;
use serde::{Deserialize, Serialize};

use crate::error::CameraResult;
use crate::time_source::TimeNs;

/// Active transport kind.
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Transport {
    /// BLE GATT control plane (always present once paired).
    Ble,
    /// Wi-Fi HTTP control + UDP MPEG-TS preview (Hero 13 AP mode).
    WifiHttp,
    /// USB-C tethered UVC webcam mode.
    UsbCUvc,
}

/// Opaque raw command bytes destined for the transport. The transport does
/// not interpret these — interpretation is the responsibility of whichever
/// module owns the protocol layer (e.g. the GoPro HTTP client).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RawCommand(pub Vec<u8>);

/// Opaque raw event bytes received from the transport.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RawEvent(pub Vec<u8>);

/// Camera transport.
///
/// Implementations own the underlying socket / GATT subscription and provide
/// a request / response surface plus an event stream.
#[async_trait]
pub trait CameraTransport: Send + Sync {
    /// Send a command and await the camera's response. The 2 s watchdog
    /// (per `docs/camera-integration-spec.md` §5.1) is enforced by the
    /// command queue, not by this trait directly — implementations should
    /// not impose their own timeout.
    async fn send_command(&self, cmd: RawCommand) -> CameraResult<RawEvent>;

    /// Await the next async event pushed from the camera (e.g. BLE
    /// notification, HTTP server-sent event). Returns `Ok(None)` on graceful
    /// shutdown and `Err(_)` on transport failure.
    async fn receive_event(&self) -> CameraResult<Option<RawEvent>>;

    /// Identify the active transport. This is observable for diagnostics
    /// and for the report PDF, which annotates "captured over 2.4 GHz Wi-Fi"
    /// vs. "captured over USB-C UVC".
    fn transport_kind(&self) -> Transport;

    /// Last-seen wall-clock timestamp of any traffic from the camera. Used
    /// by the state machine to detect link-degraded conditions; the BLE
    /// keepalive miss × 3 rule from `docs/camera-integration-spec.md` §3.3
    /// reads this field.
    fn last_seen(&self) -> TimeNs;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn transport_round_trips_through_serde() {
        let t = Transport::WifiHttp;
        let s = serde_yaml::to_string(&t).expect("serialise");
        let back: Transport = serde_yaml::from_str(&s).expect("deserialise");
        assert_eq!(t, back);
    }
}
