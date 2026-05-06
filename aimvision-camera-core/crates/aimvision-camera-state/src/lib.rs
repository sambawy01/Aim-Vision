//! Connection state machine + single-in-flight command queue for the
//! AIMVISION camera-core.
//!
//! See:
//!
//! - `docs/camera-integration-spec.md` §3 (state machine).
//! - `docs/camera-integration-spec.md` §5 (command queue).
//! - `docs/adr/0003-rust-camera-core-split.md`.

#![warn(missing_docs)]

pub mod command_queue;
pub mod state_machine;

pub use aimvision_camera_traits::ConnectionState;
pub use command_queue::{BoxedFut, CommandQueue, CommandQueueConfig, QueuedCommand};
pub use state_machine::{StateMachine, StateMachineError};
