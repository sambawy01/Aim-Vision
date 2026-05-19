//! C ABI for the phone-camera backend — slice 3c of ADR-0009.
//!
//! This module is the *only* `unsafe` surface in `aimvision-camera-phone`.
//! Everything else is safe Rust; crossing the language boundary is what
//! forces the unsafe blocks here, and each `unsafe extern "C"` function
//! documents the contract the C caller must uphold.
//!
//! # Why a hand-written C ABI (not UniFFI / cxx / etc.)
//!
//! Per ADR-0003 §"Boundary discipline": the media plane is fixed at the
//! `extern "C"` boundary because the platform shim (Swift / Kotlin) needs
//! to call it from the camera/worklet thread on every frame. UniFFI's
//! generated code adds an Arc-clone + a sync-mutex on each call, which we
//! cannot afford at 60 fps. The control plane stays on UniFFI; the media
//! plane is this file.
//!
//! # Caller contract (read me before integrating)
//!
//! The native frame-processor plugin in
//! `aimvision-mobile/plugins/phone-frame-sink/{ios,android}` is the
//! exclusive caller. The plugin is responsible for:
//!
//! 1. **Lifetime**: every handle returned by [`aimvision_phone_camera_new`]
//!    is either passed exactly once to [`aimvision_phone_camera_free`]
//!    on app termination, or leaked deliberately (a single
//!    process-lifetime camera is fine — the OS reclaims everything on
//!    exit).
//! 2. **Liveness**: after `_free` the handle is dangling; no further
//!    call may use it.
//! 3. **String validity**: the `id` argument is a pointer to a
//!    NUL-terminated, valid-UTF-8 byte sequence with a static lifetime
//!    or a lifetime that outlasts the `_new` call.
//! 4. **Audio buffer validity**: `samples_ptr` points to at least
//!    `n_samples` readable `i16`s for the duration of the
//!    `_push_audio_chunk` call. Rust copies the samples into the queue
//!    before returning — the caller may free the buffer immediately after.
//!
//! Violations are undefined behavior; the FFI does not validate beyond
//! the obvious NULL checks because the caller is in-tree.
//!
//! # Slice 3c does NOT carry pixel bytes across the boundary
//!
//! Per ADR-0003, the Rust core never touches preview pixel memory. The
//! `handle_id` argument is the platform-opaque identifier: the low 32–64
//! bits of an `IOSurface`/`AHardwareBuffer` pointer. The Rust crate
//! re-publishes that handle to downstream consumers (ML eval harnesses)
//! who own the platform-side decoding step.

#![allow(unsafe_code)]
#![allow(clippy::missing_safety_doc)]

use std::ffi::{c_char, CStr};
use std::ptr;
use std::slice;

use aimvision_camera_traits::{AudioChunk, Frame, FrameFormat};

use crate::PhoneCamera;

/// C-ABI mirror of [`FrameFormat`]. The integer discriminants are part of
/// the C ABI — never reorder, only ever append.
#[repr(u32)]
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum AimvisionFrameFormat {
    /// NV12 (Y plane + interleaved UV). Default on Vision Camera iOS + Android.
    Nv12 = 0,
    /// I420 planar YUV.
    I420 = 1,
    /// RGBA8 — synthetic / mock paths only.
    Rgba8 = 2,
}

impl From<AimvisionFrameFormat> for FrameFormat {
    fn from(f: AimvisionFrameFormat) -> Self {
        match f {
            AimvisionFrameFormat::Nv12 => FrameFormat::Nv12,
            AimvisionFrameFormat::I420 => FrameFormat::I420,
            AimvisionFrameFormat::Rgba8 => FrameFormat::Rgba8,
        }
    }
}

/// Opaque handle to a [`PhoneCamera`]. C callers must treat the layout as
/// undefined and only ever pass the pointer back to functions in this
/// module.
pub struct AimvisionPhoneCamera {
    inner: PhoneCamera,
}

/// Construct a phone-camera backend. Returns a handle the caller must
/// release with [`aimvision_phone_camera_free`].
///
/// Returns NULL if `id` is NULL or not valid UTF-8, or if either capacity
/// is zero.
#[no_mangle]
pub unsafe extern "C" fn aimvision_phone_camera_new(
    id: *const c_char,
    frame_capacity: usize,
    audio_capacity: usize,
) -> *mut AimvisionPhoneCamera {
    if id.is_null() || frame_capacity == 0 || audio_capacity == 0 {
        return ptr::null_mut();
    }
    // SAFETY: contract §3 — caller guarantees `id` is a NUL-terminated,
    // valid-UTF-8 byte sequence with a lifetime outlasting this call.
    let cstr = unsafe { CStr::from_ptr(id) };
    let Ok(id_str) = cstr.to_str() else {
        return ptr::null_mut();
    };
    let cam = PhoneCamera::new(id_str, frame_capacity, audio_capacity);
    Box::into_raw(Box::new(AimvisionPhoneCamera { inner: cam }))
}

/// Release a phone camera. Passing NULL is permitted and a no-op (so the
/// caller can free unconditionally on a possibly-failed `_new`).
#[no_mangle]
pub unsafe extern "C" fn aimvision_phone_camera_free(handle: *mut AimvisionPhoneCamera) {
    if handle.is_null() {
        return;
    }
    // SAFETY: contract §1+§2 — caller guarantees this handle was returned
    // by `_new` and has not been freed before.
    drop(unsafe { Box::from_raw(handle) });
}

/// Push a frame *handle* (not pixel bytes — see module docs).
///
/// Returns `true` if a queued frame was evicted to make room, `false`
/// otherwise. Returns `false` on a NULL handle (i.e. drops the push
/// silently — by design, the worklet thread cannot afford a panic per
/// frame).
#[no_mangle]
pub unsafe extern "C" fn aimvision_phone_camera_push_frame(
    handle: *mut AimvisionPhoneCamera,
    format: AimvisionFrameFormat,
    handle_id: u64,
    width: u32,
    height: u32,
    pts_ns: u64,
    monotonic_seq: u64,
) -> bool {
    if handle.is_null() {
        return false;
    }
    // SAFETY: contract §2 — caller guarantees the handle is live.
    let cam = unsafe { &(*handle).inner };
    cam.push_frame(Frame {
        handle_id,
        format: format.into(),
        width,
        height,
        pts_ns,
        monotonic_seq,
    })
}

/// Push a chunk of PCM audio. Samples are copied into the queue before
/// the call returns — `samples_ptr` is no longer aliased after this
/// returns.
///
/// `n_samples == 0` is permitted (degenerate empty chunk); `samples_ptr`
/// may be NULL in that case.
///
/// Returns `true` if a queued chunk was evicted, `false` otherwise.
/// Returns `false` on a NULL `handle`, or on a NULL `samples_ptr` with
/// `n_samples > 0`.
#[no_mangle]
pub unsafe extern "C" fn aimvision_phone_camera_push_audio_chunk(
    handle: *mut AimvisionPhoneCamera,
    samples_ptr: *const i16,
    n_samples: usize,
    sample_rate_hz: u32,
    channels: u8,
    start_ts_ns: u64,
) -> bool {
    if handle.is_null() {
        return false;
    }
    if samples_ptr.is_null() && n_samples > 0 {
        return false;
    }
    // SAFETY: contract §4 — caller guarantees samples_ptr is readable for
    // n_samples i16s. We copy into a Vec immediately; nothing aliases the
    // caller's buffer after this returns.
    let samples: Vec<i16> = if n_samples == 0 {
        Vec::new()
    } else {
        unsafe { slice::from_raw_parts(samples_ptr, n_samples) }.to_vec()
    };
    // SAFETY: contract §2 — caller guarantees the handle is live.
    let cam = unsafe { &(*handle).inner };
    cam.push_audio_chunk(AudioChunk {
        samples,
        sample_rate_hz,
        channels,
        start_ts_ns,
    })
}

/// Cumulative frames dropped on overflow since `_new`. Returns 0 on NULL.
#[no_mangle]
pub unsafe extern "C" fn aimvision_phone_camera_dropped_frames(
    handle: *const AimvisionPhoneCamera,
) -> u64 {
    if handle.is_null() {
        return 0;
    }
    // SAFETY: contract §2 — caller guarantees the handle is live.
    unsafe { (*handle).inner.dropped_frames() }
}

/// Cumulative audio chunks dropped on overflow since `_new`. Returns 0 on NULL.
#[no_mangle]
pub unsafe extern "C" fn aimvision_phone_camera_dropped_audio(
    handle: *const AimvisionPhoneCamera,
) -> u64 {
    if handle.is_null() {
        return 0;
    }
    // SAFETY: contract §2 — caller guarantees the handle is live.
    unsafe { (*handle).inner.dropped_audio() }
}

#[cfg(test)]
mod tests {
    //! Tests exercise the C ABI directly from Rust (legal — `extern "C"`
    //! functions can be called from Rust too). What we're checking is
    //! the *boundary behavior*: NULL handling, lifetime safety, the
    //! enum-discriminant mapping. The behavior of `PhoneCamera` itself
    //! is covered by `phone_camera::tests`.
    use super::*;
    use std::ffi::CString;

    fn make_cam(id: &str, fcap: usize, acap: usize) -> *mut AimvisionPhoneCamera {
        let c = CString::new(id).unwrap();
        // SAFETY: c outlives the call; capacities are nonzero.
        unsafe { aimvision_phone_camera_new(c.as_ptr(), fcap, acap) }
    }

    #[test]
    fn new_then_free_round_trips() {
        let h = make_cam("phone-0", 8, 8);
        assert!(!h.is_null());
        // SAFETY: h came from _new in this scope, not yet freed.
        unsafe { aimvision_phone_camera_free(h) };
    }

    #[test]
    fn new_rejects_null_id() {
        // SAFETY: passing NULL is explicitly permitted (returns NULL).
        let h = unsafe { aimvision_phone_camera_new(ptr::null(), 4, 4) };
        assert!(h.is_null());
    }

    #[test]
    fn new_rejects_zero_capacity() {
        let c = CString::new("phone-0").unwrap();
        // SAFETY: pointer is valid; zero capacities are explicitly rejected.
        let h = unsafe { aimvision_phone_camera_new(c.as_ptr(), 0, 4) };
        assert!(h.is_null());
        // SAFETY: same as above.
        let h2 = unsafe { aimvision_phone_camera_new(c.as_ptr(), 4, 0) };
        assert!(h2.is_null());
    }

    #[test]
    fn free_null_is_noop() {
        // SAFETY: NULL is explicitly permitted (documented).
        unsafe { aimvision_phone_camera_free(ptr::null_mut()) };
    }

    #[test]
    fn push_frame_records_state_visible_via_dropped_frames() {
        let h = make_cam("phone-0", 2, 2);
        // Push 4 frames into a capacity-2 queue → 2 evictions.
        for seq in 0..4u64 {
            // SAFETY: h is live; the FFI function is being called per its contract.
            let evicted = unsafe {
                aimvision_phone_camera_push_frame(
                    h,
                    AimvisionFrameFormat::Nv12,
                    seq * 1_000_000,
                    1920,
                    1080,
                    seq * 33_333_333,
                    seq,
                )
            };
            if seq < 2 {
                assert!(!evicted);
            } else {
                assert!(evicted);
            }
        }
        // SAFETY: h is live.
        let dropped = unsafe { aimvision_phone_camera_dropped_frames(h) };
        assert_eq!(dropped, 2);
        // SAFETY: h is live, then freed exactly once.
        unsafe { aimvision_phone_camera_free(h) };
    }

    #[test]
    fn push_frame_null_handle_is_noop_and_false() {
        // SAFETY: NULL handle is explicitly permitted.
        let evicted = unsafe {
            aimvision_phone_camera_push_frame(
                ptr::null_mut(),
                AimvisionFrameFormat::Nv12,
                0,
                0,
                0,
                0,
                0,
            )
        };
        assert!(!evicted);
    }

    #[test]
    fn push_audio_chunk_copies_samples_and_tracks_drops() {
        let h = make_cam("phone-0", 4, 2);
        let buf: Vec<i16> = vec![10, 20, 30, 40];
        for n in 0..4u64 {
            // SAFETY: buf outlives the call; n_samples matches buf.len().
            let evicted = unsafe {
                aimvision_phone_camera_push_audio_chunk(
                    h,
                    buf.as_ptr(),
                    buf.len(),
                    48_000,
                    1,
                    n * 10_000_000,
                )
            };
            if n < 2 {
                assert!(!evicted);
            } else {
                assert!(evicted);
            }
        }
        // SAFETY: h is live.
        let dropped = unsafe { aimvision_phone_camera_dropped_audio(h) };
        assert_eq!(dropped, 2);
        // SAFETY: h is live, then freed exactly once.
        unsafe { aimvision_phone_camera_free(h) };
    }

    #[test]
    fn push_audio_chunk_accepts_empty_buffer_with_null_ptr() {
        let h = make_cam("phone-0", 4, 4);
        // n_samples == 0 lets samples_ptr be NULL — degenerate but legal.
        // SAFETY: with n_samples = 0, samples_ptr is not dereferenced.
        let evicted =
            unsafe { aimvision_phone_camera_push_audio_chunk(h, ptr::null(), 0, 48_000, 1, 0) };
        assert!(!evicted);
        // But a NULL ptr with n_samples > 0 must be rejected.
        // SAFETY: contract violation is detected before deref.
        let rejected =
            unsafe { aimvision_phone_camera_push_audio_chunk(h, ptr::null(), 4, 48_000, 1, 0) };
        // The function returns false on the input-validation reject.
        // We can confirm nothing was queued by checking dropped_audio
        // stayed at 0 (since rejected pushes never reach the ring).
        assert!(!rejected);
        // SAFETY: h is live.
        let dropped = unsafe { aimvision_phone_camera_dropped_audio(h) };
        assert_eq!(dropped, 0);
        // SAFETY: h is live, then freed exactly once.
        unsafe { aimvision_phone_camera_free(h) };
    }

    #[test]
    fn frame_format_discriminants_are_abi_stable() {
        // These values are part of the C ABI — the C header
        // (`include/aimvision_camera_phone.h`) hard-codes them. If a
        // change here breaks this test, also update the header *and*
        // bump the soname / version per ADR-0003 §"FFI stability".
        assert_eq!(AimvisionFrameFormat::Nv12 as u32, 0);
        assert_eq!(AimvisionFrameFormat::I420 as u32, 1);
        assert_eq!(AimvisionFrameFormat::Rgba8 as u32, 2);
    }
}
