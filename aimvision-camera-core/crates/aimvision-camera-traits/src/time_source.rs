//! Clock abstraction.
//!
//! Per ADR-0003 the time source is its own trait so federation hardware
//! (PTP, GPS-disciplined) does not have to lie about its discipline through
//! the GoPro-style monotonic clock.

use serde::{Deserialize, Serialize};

/// Nanoseconds since some implementation-defined epoch.
///
/// Concrete implementations document their epoch:
/// - `MockCamera` uses session-start.
/// - `Hero13Camera` uses the BLE-broadcast clock anchor described in
///   `docs/multi-camera-sync-spec.md` §3.1.
pub type TimeNs = u64;

/// Clock-discipline tag returned by [`TimeSource::kind`].
#[derive(Copy, Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum TimeSourceKind {
    /// NTP-disciplined (phone OS clock, ~10–30 ms accuracy).
    Ntp,
    /// PTP grandmaster (sub-microsecond on a wired LAN).
    Ptp,
    /// GPS-disciplined PPS reference.
    Gps,
    /// Device-local monotonic counter; no external discipline.
    DeviceMonotonic,
}

/// Time source.
///
/// `now()` is sync because it is called on the hot path (per-frame) and
/// async overhead would be unacceptable. `kind()` is sync for the same
/// reason — the discipline does not change after construction.
pub trait TimeSource: Send + Sync {
    /// Read the current monotonic timestamp in nanoseconds.
    fn now(&self) -> TimeNs;

    /// Discipline of this clock.
    fn kind(&self) -> TimeSourceKind;
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Tiny stub used to confirm the trait is object-safe.
    struct Stub(TimeNs);

    impl TimeSource for Stub {
        fn now(&self) -> TimeNs {
            self.0
        }
        fn kind(&self) -> TimeSourceKind {
            TimeSourceKind::DeviceMonotonic
        }
    }

    #[test]
    fn time_source_is_object_safe() {
        let s: Box<dyn TimeSource> = Box::new(Stub(42));
        assert_eq!(s.now(), 42);
        assert_eq!(s.kind(), TimeSourceKind::DeviceMonotonic);
    }
}
