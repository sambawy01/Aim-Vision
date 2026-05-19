//! Dev-mode phone camera backend for the AIMVISION camera-core
//! ([ADR-0009](../../../../docs/adr/0009-phone-capture-dev-backend.md)).
//!
//! Unlike `aimvision-camera-mock` (which scripts a deterministic playback
//! from a YAML fixture) and the planned Hero 13 backend (which pulls frames
//! out of a UVC / Wi-Fi transport), the phone backend is *passive*: it
//! exposes a thread-safe `push_frame` / `push_audio_chunk` API that a
//! native shim layer on top of `react-native-vision-camera` will call from
//! the worklet thread once per camera frame.
//!
//! Slice 3a landed only the safe-Rust push API and the [`CameraMedia`]
//! impl. Slice 3c (this crate's current state) adds the [`ffi`] module:
//! a hand-written `extern "C"` C ABI that the native frame-processor
//! plugin in `aimvision-mobile/plugins/phone-frame-sink/{ios,android}`
//! calls from the Vision Camera worklet thread. See ADR-0009 §17.3c and
//! the C header at `include/aimvision_camera_phone.h`.
//!
//! # Threading model
//!
//! Push is called from the worklet thread (one writer at a time per
//! `PhoneCamera`); poll is called from the consumer thread (Rust side,
//! eventually feeding the ML eval harnesses). `PhoneCamera` is `Send +
//! Sync` and cheaply cloneable — internal state is in `Arc<Mutex<...>>`.
//!
//! # Backpressure
//!
//! Frames and audio chunks land in bounded ring buffers. When the buffer
//! is full, the *oldest* entry is dropped and the corresponding drop
//! counter increments. Dropping the oldest (rather than the newest) is
//! deliberate: the consumer wants the freshest visible state, and stale
//! frames are useless to the realtime ML pipeline. The counter lets the
//! observability layer detect chronic backpressure.

#![warn(missing_docs)]

pub mod ffi;
pub mod phone_camera;

pub use phone_camera::{PhoneCamera, PhoneCameraStats};
