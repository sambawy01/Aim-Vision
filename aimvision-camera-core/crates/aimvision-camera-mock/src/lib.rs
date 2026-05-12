//! Mock camera implementation for the AIMVISION camera-core.
//!
//! Driven by a YAML fixture (see `fixtures/sample_session.yaml`). The mock
//! implements every trait in `aimvision-camera-traits` and replays a pre-
//! scripted sequence of events deterministically.
//!
//! See:
//!
//! - `docs/camera-integration-spec.md` §12 for the fault-injection grammar.
//! - `docs/multi-camera-sync-spec.md` §8 for the synthetic 2-camera rig.
//!
//! # Why a mock at all
//!
//! Real federation hardware lands in Sprint 17. Without this mock, sync
//! code lands in Sprint 17 *and* gets validated in Sprint 17 — a 2-week
//! sprint becomes 8 weeks. With the mock available from Sprint 8, sync
//! code lands and is validated in CI by Sprint 12.

#![warn(missing_docs)]

pub mod clock;
pub mod fault_script;
pub mod mock_camera;

pub use clock::MockClock;
pub use fault_script::{ClockSpec, FaultKind, FaultScript, FaultSpec, ShotSpec};
pub use mock_camera::MockCamera;
