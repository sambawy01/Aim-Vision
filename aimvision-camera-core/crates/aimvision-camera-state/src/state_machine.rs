//! Async state machine driver.
//!
//! Wraps the pure `ConnectionState` matrix from `aimvision-camera-traits` in
//! a Tokio-driven object that:
//!
//! - Validates transitions against `allowed_transitions`.
//! - Carries the optional `CameraError` payload that the trait-layer enum
//!   does NOT carry (see `state.rs` module docs in the traits crate).
//! - Broadcasts state changes to subscribers via a Tokio watch channel.
//!
//! Transitions that are forbidden by the matrix return
//! `StateMachineError::ForbiddenTransition` rather than panicking, so
//! callers can treat them as recoverable bugs.

use std::sync::Mutex;

use aimvision_camera_traits::{CameraError, ConnectionState};
use thiserror::Error;
use tokio::sync::watch;

/// Errors emitted by the state machine when a transition is rejected.
#[derive(Debug, Error)]
pub enum StateMachineError {
    /// Caller asked for `from → to` but the matrix forbids it.
    #[error("forbidden transition {from:?} → {to:?}")]
    ForbiddenTransition {
        /// Source state.
        from: ConnectionState,
        /// Requested destination state.
        to: ConnectionState,
    },
    /// The state machine has been shut down and can no longer transition.
    #[error("state machine is shut down")]
    ShutDown,
}

/// State machine driver.
///
/// Internally uses a `tokio::sync::watch::Sender<ConnectionState>` so
/// subscribers can `await` state changes and the current state is always
/// observable without contention.
///
/// `last_error` is updated alongside transitions into `Errored`. Callers
/// inspecting state should consult both: the discriminant tells you "we are
/// errored" and `last_error()` tells you the kind.
#[derive(Debug)]
pub struct StateMachine {
    tx: watch::Sender<ConnectionState>,
    last_error: Mutex<Option<CameraError>>,
}

impl StateMachine {
    /// Create a new state machine starting in `Disconnected`.
    #[must_use]
    pub fn new() -> Self {
        let (tx, _rx) = watch::channel(ConnectionState::Disconnected);
        Self {
            tx,
            last_error: Mutex::new(None),
        }
    }

    /// Current state.
    #[must_use]
    pub fn current(&self) -> ConnectionState {
        *self.tx.borrow()
    }

    /// Subscribe to state changes. Returns a `watch::Receiver`; the latest
    /// state is always immediately readable via `.borrow()`.
    pub fn subscribe(&self) -> watch::Receiver<ConnectionState> {
        self.tx.subscribe()
    }

    /// Most recent `CameraError` recorded by the state machine, if any.
    /// Reset by the next non-`Errored` transition.
    pub fn last_error_kind(&self) -> Option<String> {
        // We can't `Clone` `CameraError` (it wraps `io::Error` which isn't
        // Clone), so we surface the display string. Internal callers can
        // call `take_last_error()` to consume the original.
        self.last_error
            .lock()
            .expect("last_error mutex poisoned")
            .as_ref()
            .map(std::string::ToString::to_string)
    }

    /// Consume and return the last error, if any.
    pub fn take_last_error(&self) -> Option<CameraError> {
        self.last_error
            .lock()
            .expect("last_error mutex poisoned")
            .take()
    }

    /// Attempt to transition to `to`. Validates against the matrix; if the
    /// transition is forbidden, returns `Err(ForbiddenTransition)` and the
    /// state is unchanged.
    pub fn transition(&self, to: ConnectionState) -> Result<(), StateMachineError> {
        let from = self.current();
        if !from.can_transition_to(to) {
            return Err(StateMachineError::ForbiddenTransition { from, to });
        }
        // Clear any prior error if we are leaving Errored or moving forward.
        if to != ConnectionState::Errored {
            *self.last_error.lock().expect("last_error mutex poisoned") = None;
        }
        // send_replace updates the slot even when there are no subscribers;
        // plain `send` would no-op without an active receiver and `current()`
        // would silently stay on the old value.
        self.tx.send_replace(to);
        tracing::debug!(?from, ?to, "state transition");
        Ok(())
    }

    /// Transition to `Errored` carrying the given `CameraError`. This is
    /// always allowed if `Errored` is in the current state's
    /// `allowed_transitions` list (which it is for every state but
    /// `Disconnected → Errored` is currently allowed too — see traits matrix).
    pub fn transition_to_errored(&self, err: CameraError) -> Result<(), StateMachineError> {
        let from = self.current();
        if !from.can_transition_to(ConnectionState::Errored) {
            return Err(StateMachineError::ForbiddenTransition {
                from,
                to: ConnectionState::Errored,
            });
        }
        *self.last_error.lock().expect("last_error mutex poisoned") = Some(err);
        self.tx.send_replace(ConnectionState::Errored);
        Ok(())
    }
}

impl Default for StateMachine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cold_start_walk() {
        let sm = StateMachine::new();
        assert_eq!(sm.current(), ConnectionState::Disconnected);
        sm.transition(ConnectionState::Discovering).expect("disc");
        sm.transition(ConnectionState::BlePairing).expect("pair");
        sm.transition(ConnectionState::BleConnected).expect("ble");
        sm.transition(ConnectionState::WifiActivating).expect("act");
        sm.transition(ConnectionState::WifiConnected).expect("wifi");
        sm.transition(ConnectionState::ReadyForRecording)
            .expect("ready");
        sm.transition(ConnectionState::Recording).expect("rec");
        assert_eq!(sm.current(), ConnectionState::Recording);
    }

    #[test]
    fn forbidden_transition_returns_error_and_keeps_state() {
        let sm = StateMachine::new();
        // Disconnected → Recording is forbidden (must walk through pairing).
        let r = sm.transition(ConnectionState::Recording);
        assert!(matches!(
            r,
            Err(StateMachineError::ForbiddenTransition { .. })
        ));
        assert_eq!(sm.current(), ConnectionState::Disconnected);
    }

    #[test]
    fn errored_path_records_kind() {
        let sm = StateMachine::new();
        sm.transition(ConnectionState::Discovering).unwrap();
        sm.transition_to_errored(CameraError::CommandTimeout { timeout_ms: 2000 })
            .expect("err");
        assert_eq!(sm.current(), ConnectionState::Errored);
        let kind = sm.last_error_kind().expect("error stored");
        assert!(kind.contains("2000"));
    }

    #[tokio::test]
    async fn watcher_observes_transitions() {
        let sm = StateMachine::new();
        let mut rx = sm.subscribe();
        sm.transition(ConnectionState::Discovering).unwrap();
        rx.changed().await.expect("rx changed");
        assert_eq!(*rx.borrow(), ConnectionState::Discovering);
    }
}
