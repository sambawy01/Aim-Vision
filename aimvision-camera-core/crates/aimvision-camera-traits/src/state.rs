//! Connection state machine.
//!
//! The `ConnectionState` enum and `allowed_transitions` matrix come straight
//! out of `docs/camera-integration-spec.md` §3. This module is the
//! single source of truth — `aimvision-camera-state` enforces transitions
//! against this matrix.
//!
//! `Errored(CameraError)` is the catch-all terminal-ish state; recovery from
//! it is per-failure-mode (see ADR-0003 §"Recovery for known failure modes")
//! and routes back through `Discovering` or `BleConnected` depending on the
//! error kind. We do NOT support `Errored → Errored` because that turns the
//! state machine into a flytrap.

/// Camera connection state.
///
/// Note: we do **not** carry the [`crate::CameraError`] variant inside the
/// enum because:
///
/// 1. The transition matrix is keyed on a discriminant, and a non-Copy
///    payload would force the matrix to allocate.
/// 2. UniFFI's tagged-enum encoding gets unwieldy when one variant carries
///    a non-Copy / non-Eq type.
///
/// Instead, the driver in `aimvision-camera-state` stores a parallel
/// `Option<CameraError>` alongside the state and surfaces it on inspection.
/// The `Errored` variant here is just the discriminant.
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash)]
pub enum ConnectionState {
    /// No BLE, no Wi-Fi, no USB.
    Disconnected,
    /// BLE central scanning, advertisement filtered by GoPro service UUID.
    Discovering,
    /// Bond initiation in progress; up to 3 attempts.
    BlePairing,
    /// GATT subscriptions live; can issue settings commands.
    BleConnected,
    /// Band selected, AP credentials read, phone OS join initiated.
    WifiActivating,
    /// Port 8080 reachable, `/state` returned 200.
    WifiConnected,
    /// USB-C UVC tethered (federation tier).
    UsbcConnected,
    /// Preset loaded, preview optional, audio routed.
    ReadyForRecording,
    /// REC indicator confirmed, hilight queue armed.
    Recording,
    /// Recording explicitly paused (stock Hero 13: emulated as stop+restart).
    RecordingPaused,
    /// Post-session: enumerating + downloading.
    FileTransferring,
    /// Graceful teardown: stop preview, leave AP, BLE keepalive only.
    Disconnecting,
    /// Terminal-ish; recovery routes through this with explicit error kind
    /// stored alongside in the driver. See module docs.
    Errored,
}

impl ConnectionState {
    /// All known states. Used by exhaustive transition-matrix tests so
    /// they do not silently miss a newly-added variant.
    pub const ALL: &'static [ConnectionState] = &[
        ConnectionState::Disconnected,
        ConnectionState::Discovering,
        ConnectionState::BlePairing,
        ConnectionState::BleConnected,
        ConnectionState::WifiActivating,
        ConnectionState::WifiConnected,
        ConnectionState::UsbcConnected,
        ConnectionState::ReadyForRecording,
        ConnectionState::Recording,
        ConnectionState::RecordingPaused,
        ConnectionState::FileTransferring,
        ConnectionState::Disconnecting,
        ConnectionState::Errored,
    ];

    /// States from which we may transition to `self`. The transition table
    /// is taken from `docs/camera-integration-spec.md` §3.2 and ADR-0003
    /// "Recovery for known failure modes".
    ///
    /// Any state may transition to `Errored` on a failure, and `Errored`
    /// can recover to `Discovering` (cold restart) or `BleConnected`
    /// (transport recovery), so we encode those too.
    #[must_use]
    pub fn allowed_transitions(&self) -> &'static [ConnectionState] {
        use ConnectionState as S;
        match self {
            // Cold start. Only `Discovering` is reachable.
            S::Disconnected => &[S::Discovering, S::Errored],

            // Scanning. Either we found the camera, timed out, or the user
            // cancelled (which routes through `Disconnecting → Disconnected`).
            S::Discovering => &[S::BlePairing, S::Errored, S::Disconnecting],

            // Pairing. Success → BleConnected. Bond rejected 3× → Errored.
            S::BlePairing => &[S::BleConnected, S::Errored, S::Disconnecting],

            // BLE up. From here we either start Wi-Fi (Solo / Club),
            // skip straight to USB-C (Federation), or tear down. We also
            // re-enter from `WifiConnected` when iOS backgrounds us per
            // `docs/camera-integration-spec.md` §3.3.
            S::BleConnected => &[
                S::WifiActivating,
                S::UsbcConnected,
                S::Disconnecting,
                S::Errored,
            ],

            // Wi-Fi join in progress. Success → WifiConnected.
            S::WifiActivating => &[S::WifiConnected, S::Errored, S::Disconnecting],

            // Wi-Fi up. Becomes `ReadyForRecording` once /state returns 200.
            // Can also go back to `WifiActivating` on TCP keepalive miss
            // per Android Doze handling.
            S::WifiConnected => &[
                S::ReadyForRecording,
                S::WifiActivating,
                S::Disconnecting,
                S::Errored,
            ],

            // USB-C tethered (federation). Goes straight to ReadyForRecording.
            S::UsbcConnected => &[S::ReadyForRecording, S::Disconnecting, S::Errored],

            // Ready. Operator presses record.
            S::ReadyForRecording => &[S::Recording, S::Disconnecting, S::Errored],

            // Recording in progress. iOS background → RecordingPaused
            // (BLE keepalive only). Stop → FileTransferring. SD full or
            // shutdown → Errored.
            S::Recording => &[
                S::RecordingPaused,
                S::FileTransferring,
                S::Errored,
                S::Disconnecting,
            ],

            // Paused. Resume → Recording. Stop → FileTransferring.
            S::RecordingPaused => &[
                S::Recording,
                S::FileTransferring,
                S::Errored,
                S::Disconnecting,
            ],

            // File transfer. Done → Disconnecting. Failure → Errored.
            S::FileTransferring => &[S::Disconnecting, S::Errored],

            // Tearing down. Always lands in `Disconnected`.
            S::Disconnecting => &[S::Disconnected, S::Errored],

            // Errored. Recovery routes are explicit:
            //  - cold restart: → Discovering
            //  - link recovery (BLE survived but Wi-Fi died): → BleConnected
            //  - graceful teardown: → Disconnecting
            S::Errored => &[S::Discovering, S::BleConnected, S::Disconnecting],
        }
    }

    /// Returns `true` if `to` is a valid transition from `self`.
    #[must_use]
    pub fn can_transition_to(&self, to: ConnectionState) -> bool {
        self.allowed_transitions().contains(&to)
    }

    /// Returns `true` if this state is terminal-ish (only `Disconnected` is
    /// fully terminal; `Errored` is "terminal until `recover()`").
    #[must_use]
    pub fn is_terminal(&self) -> bool {
        matches!(self, ConnectionState::Disconnected)
    }

    /// Returns `true` if this state implies the camera is recording (so a
    /// silent `Disconnected` transition is forbidden per `docs/camera-integration-spec.md`
    /// §3.4).
    #[must_use]
    pub fn is_recording(&self) -> bool {
        matches!(
            self,
            ConnectionState::Recording | ConnectionState::RecordingPaused
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Walk every (from, to) pair and assert the matrix is internally
    /// consistent: no transition is implicitly self-referential, the matrix
    /// covers every variant in `ALL`, and `Disconnected` has exactly one
    /// outgoing edge to `Discovering` (plus `Errored`).
    #[test]
    fn full_transition_matrix_walk() {
        for &from in ConnectionState::ALL {
            let allowed = from.allowed_transitions();
            // No state may transition to itself (would mask bugs).
            assert!(
                !allowed.contains(&from),
                "{from:?} contains a self-transition"
            );

            for &to in allowed {
                // Every allowed target must be in ALL (defensive — catches
                // stale references after refactor).
                assert!(
                    ConnectionState::ALL.contains(&to),
                    "{from:?} → {to:?}: {to:?} not in ALL",
                );
            }
        }
    }

    #[test]
    fn cold_start_path_exists() {
        assert!(ConnectionState::Disconnected.can_transition_to(ConnectionState::Discovering));
        assert!(ConnectionState::Discovering.can_transition_to(ConnectionState::BlePairing));
        assert!(ConnectionState::BlePairing.can_transition_to(ConnectionState::BleConnected));
        assert!(ConnectionState::BleConnected.can_transition_to(ConnectionState::WifiActivating));
        assert!(ConnectionState::WifiActivating.can_transition_to(ConnectionState::WifiConnected));
        assert!(
            ConnectionState::WifiConnected.can_transition_to(ConnectionState::ReadyForRecording)
        );
        assert!(ConnectionState::ReadyForRecording.can_transition_to(ConnectionState::Recording));
    }

    #[test]
    fn federation_usbc_path_skips_wifi() {
        assert!(ConnectionState::BleConnected.can_transition_to(ConnectionState::UsbcConnected));
        assert!(
            ConnectionState::UsbcConnected.can_transition_to(ConnectionState::ReadyForRecording)
        );
    }

    #[test]
    fn errored_can_recover_or_disconnect() {
        let allowed = ConnectionState::Errored.allowed_transitions();
        assert!(allowed.contains(&ConnectionState::Discovering));
        assert!(allowed.contains(&ConnectionState::BleConnected));
        assert!(allowed.contains(&ConnectionState::Disconnecting));
    }

    #[test]
    fn recording_to_disconnected_is_forbidden_directly() {
        // Per spec §3.4 a recording session can never go directly to
        // Disconnected; it must transit through FileTransferring or be
        // explicitly torn down via Disconnecting.
        assert!(!ConnectionState::Recording.can_transition_to(ConnectionState::Disconnected));
        assert!(!ConnectionState::RecordingPaused.can_transition_to(ConnectionState::Disconnected));
    }

    #[test]
    fn recording_predicate_captures_both() {
        assert!(ConnectionState::Recording.is_recording());
        assert!(ConnectionState::RecordingPaused.is_recording());
        assert!(!ConnectionState::ReadyForRecording.is_recording());
        assert!(!ConnectionState::FileTransferring.is_recording());
    }

    #[test]
    fn ios_background_path_recording_to_recording_paused() {
        // Per spec §3.3 we transition `Recording → RecordingPaused` and back
        // when iOS backgrounds; that round trip must be allowed.
        assert!(ConnectionState::Recording.can_transition_to(ConnectionState::RecordingPaused));
        assert!(ConnectionState::RecordingPaused.can_transition_to(ConnectionState::Recording));
    }

    #[test]
    fn android_doze_path_wifi_connected_back_to_wifi_activating() {
        // Per spec §3.3 we re-enter `WifiActivating` from `WifiConnected`
        // on TCP keepalive miss without dropping BLE.
        assert!(ConnectionState::WifiConnected.can_transition_to(ConnectionState::WifiActivating));
    }

    #[test]
    fn disconnected_is_terminal() {
        assert!(ConnectionState::Disconnected.is_terminal());
        assert!(!ConnectionState::Errored.is_terminal());
    }
}
