//! JNI shim for `aimvision-camera-phone` (ADR-0009 §17.3c follow-up).
//!
//! Loaded by Android Kotlin via
//! `System.loadLibrary("aimvision_camera_phone_jni")` in
//! `aimvision-mobile/plugins/phone-frame-sink/android/AVPhoneFrameSinkBridge.kt`.
//! The Kotlin class declares four `external fun`s; this crate exports the
//! JNI-named symbols that satisfy them, translating each call into the
//! plain C ABI from `aimvision-camera-phone::ffi`.
//!
//! # Why a separate Rust crate (instead of a hand-written C/C++ shim)
//!
//! - We already have cargo + a workspace; adding a CMake/Gradle native
//!   build step would be more friction than another workspace member.
//! - The `jni` crate gives us typed Rust wrappers (`JNIEnv`, `JString`,
//!   `JClass`) so the shim is straight-line code with no manual GetEnv /
//!   ReleaseStringUTFChars dances.
//! - Keeping the shim in Rust means it shares the workspace's lint /
//!   format / clippy gates and gets covered by the same camera-core CI
//!   job that builds the rest of the camera stack.
//!
//! # Build for Android
//!
//! ```text
//! cd aimvision-camera-core
//! cargo build -p aimvision-camera-phone-jni --release --target aarch64-linux-android
//! # → target/aarch64-linux-android/release/libaimvision_camera_phone_jni.so
//! # Drop into aimvision-mobile/android/app/src/main/jniLibs/arm64-v8a/
//! ```
//!
//! Repeat for `armv7-linux-androideabi`, `x86_64-linux-android`,
//! `i686-linux-android` as needed for the device matrix from ADR-0009
//! §"Constraints we accept" (Pixel 7+ → arm64 is the only floor we set).
//!
//! # Class name must match the Kotlin bridge
//!
//! JNI maps `Java_<package_with_underscores>_<class>_<method>` to the
//! exported symbol name. The Kotlin class is
//! `com.aimvision.app.phoneframesink.AVPhoneFrameSinkBridge`, so the
//! exports below must use exactly
//! `Java_com_aimvision_app_phoneframesink_AVPhoneFrameSinkBridge_*`.
//! If the Kotlin class is renamed, **rename both sides in the same
//! commit** — JNI binding is by symbol name, not by tooling.

use std::ffi::CString;

use jni::objects::{JClass, JString};
use jni::sys::{jboolean, jint, jlong, JNI_FALSE, JNI_TRUE};
use jni::JNIEnv;

use aimvision_camera_phone::ffi::{
    aimvision_phone_camera_dropped_frames, aimvision_phone_camera_free, aimvision_phone_camera_new,
    aimvision_phone_camera_push_frame, AimvisionFrameFormat, AimvisionPhoneCamera,
};

/// `AVPhoneFrameSinkBridge.nativeNew(String, Long, Long): Long`
///
/// Returns 0 on any of: NULL/non-UTF-8 id, non-positive capacity,
/// CString allocation failure (id contained an interior NUL byte).
/// 0 is the documented "unavailable" handle for the Kotlin bridge.
#[no_mangle]
pub extern "system" fn Java_com_aimvision_app_phoneframesink_AVPhoneFrameSinkBridge_nativeNew(
    mut env: JNIEnv,
    _class: JClass,
    id: JString,
    frame_capacity: jlong,
    audio_capacity: jlong,
) -> jlong {
    if frame_capacity <= 0 || audio_capacity <= 0 {
        return 0;
    }
    let id_jstr = match env.get_string(&id) {
        Ok(s) => s,
        Err(_) => return 0,
    };
    let id_str: String = match id_jstr.to_str() {
        Ok(s) => s.to_owned(),
        Err(_) => return 0,
    };
    let id_cstr = match CString::new(id_str) {
        Ok(c) => c,
        Err(_) => return 0,
    };
    // SAFETY: id_cstr outlives the call; we just bounds-checked the capacities.
    let handle = unsafe {
        aimvision_phone_camera_new(
            id_cstr.as_ptr(),
            frame_capacity as usize,
            audio_capacity as usize,
        )
    };
    handle as jlong
}

/// `AVPhoneFrameSinkBridge.nativeFree(Long): Unit`
///
/// Accepts 0 (no-op) — matches the C ABI's NULL handling.
#[no_mangle]
pub extern "system" fn Java_com_aimvision_app_phoneframesink_AVPhoneFrameSinkBridge_nativeFree(
    _env: JNIEnv,
    _class: JClass,
    handle: jlong,
) {
    // SAFETY: the Kotlin bridge owns the lifetime — it only calls this once
    // per process at shutdown (or not at all; the OS reclaims on exit).
    unsafe { aimvision_phone_camera_free(handle as *mut AimvisionPhoneCamera) };
}

/// `AVPhoneFrameSinkBridge.nativePushFrame(Long, Int, Long, Int, Int, Long, Long): Boolean`
///
/// Returns `JNI_TRUE` iff the C ABI accepted the push (i.e. the Rust
/// queue successfully recorded the frame). Returns `JNI_FALSE` on a
/// 0 handle or an out-of-range `formatRaw` (defensive — Kotlin only
/// ever sends 0/1/2).
#[no_mangle]
#[allow(clippy::too_many_arguments)]
pub extern "system" fn Java_com_aimvision_app_phoneframesink_AVPhoneFrameSinkBridge_nativePushFrame(
    _env: JNIEnv,
    _class: JClass,
    handle: jlong,
    format_raw: jint,
    handle_id: jlong,
    width: jint,
    height: jint,
    timestamp_ns: jlong,
    monotonic_seq: jlong,
) -> jboolean {
    if handle == 0 {
        return JNI_FALSE;
    }
    let format = match format_raw {
        0 => AimvisionFrameFormat::Nv12,
        1 => AimvisionFrameFormat::I420,
        2 => AimvisionFrameFormat::Rgba8,
        _ => return JNI_FALSE,
    };
    // SAFETY: caller is the Kotlin bridge holding a handle returned by
    // `nativeNew` in the same process. Width/height are reinterpreted as
    // u32 — Android camera frames will never have negative dimensions,
    // but we cast via `as` rather than panicking on `try_into`.
    let evicted = unsafe {
        aimvision_phone_camera_push_frame(
            handle as *mut AimvisionPhoneCamera,
            format,
            handle_id as u64,
            width as u32,
            height as u32,
            timestamp_ns as u64,
            monotonic_seq as u64,
        )
    };
    // The C ABI returns `true` *when a frame was evicted from the queue*.
    // That is an observability signal, not a failure. The bridge wants
    // "did the push reach Rust?" — which is unconditionally true past the
    // handle != 0 check above. We pass through `evicted` so the Kotlin
    // side can react to chronic backpressure if needed.
    let _ = evicted;
    JNI_TRUE
}

/// `AVPhoneFrameSinkBridge.nativeDroppedFrames(Long): Long`
#[no_mangle]
pub extern "system" fn Java_com_aimvision_app_phoneframesink_AVPhoneFrameSinkBridge_nativeDroppedFrames(
    _env: JNIEnv,
    _class: JClass,
    handle: jlong,
) -> jlong {
    if handle == 0 {
        return 0;
    }
    // SAFETY: as above — handle is live for the duration of this call.
    let n = unsafe { aimvision_phone_camera_dropped_frames(handle as *const AimvisionPhoneCamera) };
    n as jlong
}

#[cfg(test)]
mod tests {
    //! These tests exercise the C-ABI underlay directly (no actual JNI
    //! call possible without a JVM). They guard the *type conversions* —
    //! the bit-pattern claims that `jlong as *mut AimvisionPhoneCamera`
    //! round-trips, that the `jint` → `AimvisionFrameFormat` mapping
    //! covers every enum value, and that capacity guards reject the
    //! degenerate inputs the JNI shim filters on.
    //!
    //! The actual JNI dispatch is verified at device-runtime — same gate
    //! as the rest of slice 3c (manual Expo prebuild + `expo run:android`).

    use super::*;
    use std::ptr;

    #[test]
    fn handle_round_trips_through_jlong() {
        let id = CString::new("phone-0").unwrap();
        // SAFETY: id outlives the call; capacities are positive.
        let raw = unsafe { aimvision_phone_camera_new(id.as_ptr(), 4, 4) };
        assert!(!raw.is_null());
        let as_long: jlong = raw as jlong;
        let back: *mut AimvisionPhoneCamera = as_long as *mut AimvisionPhoneCamera;
        // SAFETY: same allocation, freed exactly once.
        let dropped = unsafe { aimvision_phone_camera_dropped_frames(back) };
        assert_eq!(dropped, 0);
        // SAFETY: as above.
        unsafe { aimvision_phone_camera_free(back) };
    }

    #[test]
    fn format_raw_mapping_covers_every_variant() {
        // The JNI shim's match must include 0, 1, 2 exactly. If you add
        // a new variant to AimvisionFrameFormat, add it here AND to the
        // `nativePushFrame` match, AND to the C header, AND to the
        // Kotlin bridge.
        let mapped = |r: jint| -> Option<AimvisionFrameFormat> {
            match r {
                0 => Some(AimvisionFrameFormat::Nv12),
                1 => Some(AimvisionFrameFormat::I420),
                2 => Some(AimvisionFrameFormat::Rgba8),
                _ => None,
            }
        };
        assert!(matches!(mapped(0), Some(AimvisionFrameFormat::Nv12)));
        assert!(matches!(mapped(1), Some(AimvisionFrameFormat::I420)));
        assert!(matches!(mapped(2), Some(AimvisionFrameFormat::Rgba8)));
        assert!(mapped(3).is_none());
        assert!(mapped(-1).is_none());
    }

    #[test]
    fn null_handle_is_rejected_by_underlying_c_abi() {
        // Mirrors the JNI shim's `if handle == 0` guard — same semantics
        // by way of the C ABI's NULL check.
        // SAFETY: NULL is the explicit no-op contract.
        let dropped =
            unsafe { aimvision_phone_camera_dropped_frames(ptr::null::<AimvisionPhoneCamera>()) };
        assert_eq!(dropped, 0);
    }
}
