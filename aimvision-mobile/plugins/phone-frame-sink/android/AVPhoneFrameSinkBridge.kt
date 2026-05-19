/*
 * AVPhoneFrameSinkBridge.kt
 *
 * Slice 3c of ADR-0009 — Kotlin/JNI bridge into the Rust
 * `aimvision-camera-phone` crate's C ABI (see
 * ../../../../aimvision-camera-core/crates/aimvision-camera-phone/include/
 * aimvision_camera_phone.h).
 *
 * # Why this is a singleton with a `loadLibrary` try/catch
 *
 * The Rust crate ships as `libaimvision_camera_phone.so`. JNI requires
 * `Java_<package>_<class>_<method>`-named exports, which the bare C ABI
 * does NOT have — so a small JNI C-shim (`libaimvision_camera_phone_jni.so`)
 * is required between Kotlin and the C ABI. That shim is a follow-up
 * sub-slice (3c-android-jni); until it lands, `System.loadLibrary`
 * raises `UnsatisfiedLinkError` and the bridge reports unavailable —
 * the Vision Camera plugin falls back to the metadata-only path from
 * slice 3b, matching the iOS dlsym fallback in `AVPhoneFrameSinkBridge.swift`.
 *
 * # External function naming
 *
 * The `external fun` signatures here are the JNI-side contract the
 * follow-up shim must implement. They mirror the C ABI 1:1 in argument
 * order; the shim translates the `Long` opaque handle into a
 * `AimvisionPhoneCamera*` and forwards the call.
 *
 * # Lifecycle
 *
 * Process-singleton: one `PhoneCamera` per app, never freed (OS cleans up
 * on process exit). Matches the iOS bridge.
 */

package com.aimvision.app.phoneframesink

object AVPhoneFrameSinkBridge {
    @Volatile
    private var loaded: Boolean = false

    @Volatile
    private var cameraHandle: Long = 0L

    @Volatile
    private var monotonicSeq: Long = 0L

    init {
        try {
            // The JNI shim shipped from `aimvision-camera-phone-jni`
            // (follow-up sub-slice) is what hosts the `Java_..._native*`
            // exports declared below. Until that ships this loadLibrary
            // raises and we stay in the "unavailable" state.
            System.loadLibrary("aimvision_camera_phone_jni")
            cameraHandle = nativeNew("phone-0", 64L, 32L)
            loaded = cameraHandle != 0L
        } catch (_: UnsatisfiedLinkError) {
            // Expected on day zero — bridge reports unavailable, plugin
            // falls back to metadata-only output.
            loaded = false
            cameraHandle = 0L
        } catch (_: Throwable) {
            // Defensive: any other init failure also fails-soft. A
            // broken bridge must not crash the app.
            loaded = false
            cameraHandle = 0L
        }
    }

    /**
     * True iff the JNI shim was loaded AND the Rust `_new` call returned
     * a non-zero handle. When false the plugin must not call
     * [pushFrameMetadata].
     */
    @JvmStatic
    fun isAvailable(): Boolean = loaded

    /**
     * Per-camera wrap-safe monotonic frame counter. Single worklet thread
     * caller; the `@Synchronized` is defensive against future migrations
     * to a multi-thread emitter.
     */
    @JvmStatic
    @Synchronized
    fun nextMonotonicSeq(): Long {
        monotonicSeq += 1L
        return monotonicSeq
    }

    /**
     * Push one frame metadata record to Rust. Returns `true` on a
     * successful push, `false` when the bridge is unavailable.
     */
    @JvmStatic
    fun pushFrameMetadata(
        formatRaw: Int,
        handleId: Long,
        width: Int,
        height: Int,
        timestampNs: Long,
        monotonicSeq: Long,
    ): Boolean {
        if (!loaded || cameraHandle == 0L) return false
        nativePushFrame(cameraHandle, formatRaw, handleId, width, height, timestampNs, monotonicSeq)
        return true
    }

    /** Cumulative dropped-frames counter from the Rust ring buffer. */
    @JvmStatic
    fun droppedFramesCount(): Long {
        if (!loaded || cameraHandle == 0L) return 0L
        return nativeDroppedFrames(cameraHandle)
    }

    // JNI exports — implemented by the follow-up JNI shim
    // `libaimvision_camera_phone_jni.so`. The shim translates the opaque
    // `Long` handle into a `AimvisionPhoneCamera*` and forwards to the
    // C ABI in `aimvision_camera_phone.h`.
    @JvmStatic
    private external fun nativeNew(id: String, frameCapacity: Long, audioCapacity: Long): Long

    @JvmStatic
    @Suppress("UnusedPrivateMember")
    private external fun nativeFree(handle: Long)

    @JvmStatic
    private external fun nativePushFrame(
        handle: Long,
        formatRaw: Int,
        handleId: Long,
        width: Int,
        height: Int,
        timestampNs: Long,
        monotonicSeq: Long,
    ): Boolean

    @JvmStatic
    private external fun nativeDroppedFrames(handle: Long): Long
}
