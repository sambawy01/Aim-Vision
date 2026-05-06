//! Deterministic mock clock with skew + drift injection.
//!
//! `MockClock` implements `TimeSource` and is driven by an external "advance"
//! call (rather than wall-clock time) so tests are reproducible.
//!
//! ## Skew + drift model
//!
//! ```text
//!   t_camera(t_real) = t_real + skew_ns + drift_ppm * t_real
//! ```
//!
//! where `t_real` is the deterministic "session time" the test advances and
//! `drift_ppm` is parts-per-million linear drift. The model matches the
//! synthetic rig spec (`docs/multi-camera-sync-spec.md` §8).

use std::sync::Mutex;

use aimvision_camera_traits::{TimeNs, TimeSource, TimeSourceKind};

/// Mock clock with skew and drift injection.
///
/// Internally uses a `Mutex<u64>` for the session time so multiple readers
/// see a consistent value even when the test driver advances it from a
/// different task. The mutex is uncontended in practice (advances are rare
/// vs. reads).
#[derive(Debug)]
pub struct MockClock {
    skew_ns: i64,
    drift_ppm: f64,
    session_time_ns: Mutex<u64>,
}

impl MockClock {
    /// Construct a new mock clock with given constant skew (in milliseconds)
    /// and linear drift (parts per million, i.e. ns of error per millisecond).
    #[must_use]
    pub fn new(skew_ms: f64, drift_ms_per_min: f64) -> Self {
        // ms-per-minute → ppm: 1 ms / 60_000 ms = 16.67 ppm per ms-per-minute
        let drift_ppm = drift_ms_per_min * 1_000.0 / 60_000.0 * 1_000.0;
        Self {
            skew_ns: (skew_ms * 1_000_000.0) as i64,
            drift_ppm,
            session_time_ns: Mutex::new(0),
        }
    }

    /// Advance session time by `delta_ns` nanoseconds.
    pub fn advance(&self, delta_ns: u64) {
        let mut t = self
            .session_time_ns
            .lock()
            .expect("mock clock mutex poisoned");
        *t = t.saturating_add(delta_ns);
    }

    /// Set absolute session time. Tests that "jump" ahead use this.
    pub fn set_session_time(&self, t_ns: u64) {
        let mut t = self
            .session_time_ns
            .lock()
            .expect("mock clock mutex poisoned");
        *t = t_ns;
    }

    /// Read the underlying session time without skew/drift applied.
    /// Used by the fault-script player for "ground truth" comparisons.
    pub fn ground_truth_ns(&self) -> u64 {
        *self
            .session_time_ns
            .lock()
            .expect("mock clock mutex poisoned")
    }

    /// Apply the skew + drift model to a session-time value to get the
    /// camera-clock value this clock would report.
    fn apply_skew_drift(&self, session_ns: u64) -> u64 {
        // drift contribution: drift_ppm * session_ns / 1_000_000
        let drift_ns = (self.drift_ppm * session_ns as f64 / 1_000_000.0) as i64;
        let raw = session_ns as i64 + self.skew_ns + drift_ns;
        // Clamp to non-negative; in practice tests never advance to a point
        // where session_ns + skew_ns is negative because skew is bounded.
        raw.max(0) as u64
    }
}

impl TimeSource for MockClock {
    fn now(&self) -> TimeNs {
        let session_ns = self.ground_truth_ns();
        self.apply_skew_drift(session_ns)
    }

    fn kind(&self) -> TimeSourceKind {
        TimeSourceKind::DeviceMonotonic
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zero_skew_zero_drift_is_identity() {
        let c = MockClock::new(0.0, 0.0);
        c.advance(1_000_000_000);
        assert_eq!(c.now(), 1_000_000_000);
        assert_eq!(c.ground_truth_ns(), 1_000_000_000);
    }

    #[test]
    fn skew_offsets_now() {
        // 15 ms skew → 15_000_000 ns added to every read.
        let c = MockClock::new(15.0, 0.0);
        c.advance(1_000_000_000);
        assert_eq!(c.now(), 1_015_000_000);
    }

    #[test]
    fn drift_accumulates_linearly() {
        // 2 ms/min drift = 33.33 ppm. After 60 s of session time the camera
        // clock should be ~2 ms ahead of session time.
        let c = MockClock::new(0.0, 2.0);
        c.advance(60_000_000_000); // 60 s
        let now = c.now();
        let drift = now as i64 - 60_000_000_000_i64;
        // Allow ±1% tolerance on the drift math (float roundoff).
        assert!(
            (drift - 2_000_000).abs() < 20_000,
            "expected ~2_000_000 ns drift, got {drift}"
        );
    }

    #[test]
    fn negative_skew_does_not_underflow() {
        let c = MockClock::new(-5.0, 0.0);
        // session = 0, skew = -5_000_000 → clamped to 0
        assert_eq!(c.now(), 0);
    }
}
