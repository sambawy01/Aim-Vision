//! Pure trait surface for the AIMVISION camera-core.
//!
//! This crate intentionally contains no implementations. It is the contract
//! between the app layer (iOS/Android via UniFFI, Linux on-prem appliance
//! native) and concrete camera implementations (`Hero13Camera`, `MockCamera`,
//! future `Insta360X4Camera`, custom `AimvisionHardwareCamera`).
//!
//! See [ADR-0003](../../../../docs/adr/0003-rust-camera-core-split.md) for the
//! split rationale: a single fat `Camera` trait does not survive contact with
//! Insta360 X4 (a 360 stitch, not a flat sensor) or future hardware with
//! different clock disciplines.
//!
//! # Trait Layout
//!
//! - [`CameraControl`]    — recording, hilights, settings, capability query.
//! - [`CameraTransport`]  — BLE / Wi-Fi / USB-C UVC link layer.
//! - [`CameraMedia`]      — preview frames, audio PCM, MP4 download.
//! - [`TimeSource`]       — clock discipline (NTP / PTP / GPS / device monotonic).
//!
//! Implementations declare a [`CameraCapabilities`] struct so the app queries
//! "does this camera support hilight?" rather than discovering it through an
//! `Err(Unsupported)`.

#![cfg_attr(docsrs, feature(doc_cfg))]
#![warn(missing_docs)]

pub mod capabilities;
pub mod control;
pub mod error;
pub mod events;
pub mod media;
pub mod state;
pub mod time_source;
pub mod transport;

pub use capabilities::{CameraCapabilities, MultiCamSyncProtocol, Resolution};
pub use control::{CameraControl, CaptureMode, RecordingHandle, SettingId, SettingValue};
pub use error::{CameraError, CameraResult};
pub use events::{CameraEvent, FileId, ThermalState, VendorEvent};
pub use media::{AudioChunk, CameraMedia, Frame, FrameFormat, MediaSink};
pub use state::ConnectionState;
pub use time_source::{TimeNs, TimeSource, TimeSourceKind};
pub use transport::{CameraTransport, RawCommand, RawEvent, Transport};
