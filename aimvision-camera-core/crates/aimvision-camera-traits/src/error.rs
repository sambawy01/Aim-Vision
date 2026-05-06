//! Camera error types.
//!
//! `CameraError` is the canonical error returned across every trait in this
//! crate. It is `thiserror`-derived and crosses the UniFFI boundary as a
//! tagged enum on the Swift / Kotlin side.
//!
//! # Variants
//!
//! - [`CameraError::Bonded`] — the camera was bonded to a different phone.
//!   Recovery requires the BLE bond-clearing flow described in
//!   `docs/camera-integration-spec.md` §4.
//! - [`CameraError::WifiBackgroundedByOs`] — iOS / Android suspended the
//!   Wi-Fi association while the app was backgrounded. Recovery is to
//!   transition `Disconnecting → BleConnected` and rejoin on foreground.
//! - [`CameraError::CommandTimeout`] — the 2 s watchdog from the command queue.
//! - [`CameraError::FirmwareUntested`] — the firmware version is not in our
//!   tested matrix; sessions are refused unless the build is debug.
//! - [`CameraError::Unsupported`] — capability the implementation does not
//!   provide. Callers should query [`CameraCapabilities`](crate::CameraCapabilities)
//!   instead of relying on this.
//! - [`CameraError::Cancelled`] — propagated cancellation token.
//! - [`CameraError::Vendor`] — vendor-defined error string. Never a control
//!   path — purely diagnostic.

use std::io;

use thiserror::Error;

/// Result alias used across the camera-core trait surface.
pub type CameraResult<T> = Result<T, CameraError>;

/// Canonical camera error.
///
/// This enum is `non_exhaustive` so adding new vendor-specific variants is
/// not a breaking change.
#[derive(Debug, Error)]
#[non_exhaustive]
pub enum CameraError {
    /// The camera is bonded to a different phone; bond cache must be cleared.
    #[error("camera is bonded to another device; clear bond and re-pair")]
    Bonded,

    /// Bond-clearing failed despite the documented `Unpair All` opcode.
    #[error("failed to clear BLE bond cache: {0}")]
    BondClearFailed(String),

    /// The OS backgrounded the app and tore down the Wi-Fi association.
    /// Per `docs/camera-integration-spec.md` §3.3 this is a structured
    /// transition through `Disconnecting → BleConnected`, not a generic retry.
    #[error("Wi-Fi association torn down by OS while backgrounded")]
    WifiBackgroundedByOs,

    /// The command queue's per-command watchdog fired (default 2 s).
    #[error("command timed out after {timeout_ms}ms")]
    CommandTimeout {
        /// Watchdog deadline in milliseconds.
        timeout_ms: u64,
    },

    /// The connected camera firmware is not in the tested matrix.
    /// Production builds refuse sessions on `untested` firmware.
    #[error("camera firmware {version} is not in the tested matrix")]
    FirmwareUntested {
        /// Firmware version string as read from the BLE Query service.
        version: String,
    },

    /// Capability is not supported on this camera. Callers should consult
    /// [`CameraCapabilities`](crate::CameraCapabilities) before calling.
    #[error("capability not supported: {0}")]
    Unsupported(&'static str),

    /// Underlying transport / IO error (BLE GATT, HTTP, USB, file).
    #[error("transport error: {0}")]
    Transport(#[from] io::Error),

    /// YAML parse failure from the mock fault-script grammar.
    #[error("yaml error: {0}")]
    Yaml(#[from] serde_yaml::Error),

    /// Operation cancelled via cancellation token.
    #[error("operation cancelled")]
    Cancelled,

    /// Vendor-specific error wrapped as a string (sealed escape hatch).
    #[error("vendor error: {0}")]
    Vendor(String),
}

impl CameraError {
    /// Returns `true` if the error is plausibly retryable by the command
    /// queue's exponential-backoff policy. Watchdog timeouts and transient
    /// transport errors are retryable; bond-cache and firmware errors are not.
    #[must_use]
    pub fn is_retryable(&self) -> bool {
        matches!(
            self,
            CameraError::CommandTimeout { .. }
                | CameraError::Transport(_)
                | CameraError::WifiBackgroundedByOs
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn retryable_classification() {
        assert!(CameraError::CommandTimeout { timeout_ms: 2000 }.is_retryable());
        assert!(CameraError::WifiBackgroundedByOs.is_retryable());
        assert!(!CameraError::Bonded.is_retryable());
        assert!(!CameraError::FirmwareUntested {
            version: "v02.00.00".into()
        }
        .is_retryable());
        assert!(!CameraError::Unsupported("hilight").is_retryable());
    }

    #[test]
    fn display_renders_useful_messages() {
        let e = CameraError::CommandTimeout { timeout_ms: 2000 };
        assert!(e.to_string().contains("2000"));
        let e = CameraError::FirmwareUntested {
            version: "v02.00.00".into(),
        };
        assert!(e.to_string().contains("v02.00.00"));
    }
}
