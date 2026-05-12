//! Exhaustive transition matrix tests for the state machine.
//!
//! Walks every (from, to) pair across the full `ConnectionState` enum and
//! asserts the state machine's `transition()` agrees with the trait-layer
//! `allowed_transitions()` matrix.

use aimvision_camera_state::{ConnectionState, StateMachine, StateMachineError};
use aimvision_camera_traits::CameraError;

/// Drive the state machine into `target` via a known-valid path. Returns
/// `None` if no path is implemented in the test harness; not every state
/// is reachable in fewer than 3 hops without a session re-entry, so we
/// keep this table explicit.
fn walk_to(sm: &StateMachine, target: ConnectionState) -> Option<()> {
    use ConnectionState as S;
    // Reset to Disconnected by going through Disconnecting if needed.
    if sm.current() != S::Disconnected {
        // Hard reset — only the test driver ever does this.
        let _ = sm.transition(S::Disconnecting);
        let _ = sm.transition(S::Disconnected);
    }
    match target {
        S::Disconnected => Some(()),
        S::Discovering => sm.transition(S::Discovering).ok(),
        S::BlePairing => {
            sm.transition(S::Discovering).ok()?;
            sm.transition(S::BlePairing).ok()
        }
        S::BleConnected => {
            sm.transition(S::Discovering).ok()?;
            sm.transition(S::BlePairing).ok()?;
            sm.transition(S::BleConnected).ok()
        }
        S::WifiActivating => {
            walk_to(sm, S::BleConnected)?;
            sm.transition(S::WifiActivating).ok()
        }
        S::WifiConnected => {
            walk_to(sm, S::WifiActivating)?;
            sm.transition(S::WifiConnected).ok()
        }
        S::UsbcConnected => {
            walk_to(sm, S::BleConnected)?;
            sm.transition(S::UsbcConnected).ok()
        }
        S::ReadyForRecording => {
            walk_to(sm, S::WifiConnected)?;
            sm.transition(S::ReadyForRecording).ok()
        }
        S::Recording => {
            walk_to(sm, S::ReadyForRecording)?;
            sm.transition(S::Recording).ok()
        }
        S::RecordingPaused => {
            walk_to(sm, S::Recording)?;
            sm.transition(S::RecordingPaused).ok()
        }
        S::FileTransferring => {
            walk_to(sm, S::Recording)?;
            sm.transition(S::FileTransferring).ok()
        }
        S::Disconnecting => {
            walk_to(sm, S::ReadyForRecording)?;
            sm.transition(S::Disconnecting).ok()
        }
        S::Errored => {
            walk_to(sm, S::Discovering)?;
            sm.transition_to_errored(CameraError::Cancelled).ok()
        }
    }
}

#[test]
fn every_allowed_transition_is_accepted_by_state_machine() {
    for &from in ConnectionState::ALL {
        for &to in from.allowed_transitions() {
            let sm = StateMachine::new();
            walk_to(&sm, from).unwrap_or_else(|| panic!("walk to {from:?} failed"));
            assert_eq!(
                sm.current(),
                from,
                "walk landed on {:?} not {:?}",
                sm.current(),
                from
            );

            let result = if to == ConnectionState::Errored {
                sm.transition_to_errored(CameraError::Cancelled)
            } else {
                sm.transition(to)
            };
            assert!(
                result.is_ok(),
                "{from:?} → {to:?} was rejected by state machine but allowed by matrix"
            );
            assert_eq!(sm.current(), to);
        }
    }
}

#[test]
fn every_disallowed_transition_is_rejected_by_state_machine() {
    for &from in ConnectionState::ALL {
        for &to in ConnectionState::ALL {
            // Allowed transitions are tested above. Self-transitions are
            // forbidden by the matrix and we don't need to assert them
            // separately here.
            if from.can_transition_to(to) {
                continue;
            }
            if from == to {
                continue;
            }
            let sm = StateMachine::new();
            if walk_to(&sm, from).is_none() {
                continue;
            }
            assert_eq!(sm.current(), from);

            let result = sm.transition(to);
            assert!(
                matches!(result, Err(StateMachineError::ForbiddenTransition { .. })),
                "{from:?} → {to:?} should have been rejected but was: {result:?}"
            );
            assert_eq!(
                sm.current(),
                from,
                "rejected transition mutated state from {from:?}",
            );
        }
    }
}

#[test]
fn errored_to_disconnected_is_not_a_direct_path() {
    // Per spec §3.4, Errored cannot collapse straight to Disconnected;
    // it must route through Disconnecting.
    let sm = StateMachine::new();
    sm.transition(ConnectionState::Discovering).unwrap();
    sm.transition_to_errored(CameraError::Cancelled).unwrap();
    let r = sm.transition(ConnectionState::Disconnected);
    assert!(matches!(
        r,
        Err(StateMachineError::ForbiddenTransition { .. })
    ));
    sm.transition(ConnectionState::Disconnecting).unwrap();
    sm.transition(ConnectionState::Disconnected).unwrap();
    assert_eq!(sm.current(), ConnectionState::Disconnected);
}
