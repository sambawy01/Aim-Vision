/*
 * AVPhoneFrameSink.kt
 *
 * Android half of the AIMVISION phone-capture native plugin (ADR-0009).
 * Mirror of the iOS class in `../ios/AVPhoneFrameSink.swift`.
 *
 * Vision Camera v4 surfaces every camera frame to subclasses of
 * `FrameProcessorPlugin`. The `callback()` runs on the Vision Camera
 * worklet thread; we return a metadata map back to the JS worklet, and
 * (slice 3c) also forward the frame metadata to the Rust
 * `aimvision-camera-phone` crate via the JNI bridge in
 * `AVPhoneFrameSinkBridge.kt`. The bridge fails-soft when the JNI shim
 * `libaimvision_camera_phone_jni.so` isn't bundled yet, so the plugin
 * keeps working with metadata-only output on day zero.
 *
 * The companion package class `AVPhoneFrameSinkPackage` is what React
 * Native autolinking finds; the Expo config plugin in
 * `plugins/phone-frame-sink/withPhoneFrameSink.ts` ensures it's registered
 * in MainApplication.
 */

package com.aimvision.app.phoneframesink

import com.mrousavy.camera.frameprocessors.Frame
import com.mrousavy.camera.frameprocessors.FrameProcessorPlugin
import com.mrousavy.camera.frameprocessors.VisionCameraProxy

class AVPhoneFrameSink(
    @Suppress("UNUSED_PARAMETER") proxy: VisionCameraProxy,
    @Suppress("UNUSED_PARAMETER") options: Map<String, Any>?,
) : FrameProcessorPlugin() {
    override fun callback(frame: Frame, arguments: Map<String, Any>?): Any? {
        val width: Int = frame.width
        val height: Int = frame.height
        val timestampNs: Long = frame.timestamp
        val seq = AVPhoneFrameSinkBridge.nextMonotonicSeq()

        // Vision Camera v4 doesn't expose a uniform pixelFormat enum
        // across Android camera2 modes; default to NV12 (the canonical
        // ImageReader format) and let the Rust consumer reformat if a
        // downstream stage needs another layout.
        val formatRaw = 0 // AIMVISION_FRAME_FORMAT_NV12

        // No AHardwareBuffer pointer is reachable from this slice of the
        // Vision Camera API surface, so ferry the timestamp as a
        // stand-in identifier (matches the iOS handleId fallback). The
        // follow-up sub-slice that wires real AHardwareBuffer handles
        // will replace this.
        val handleId = timestampNs

        val pushed = AVPhoneFrameSinkBridge.pushFrameMetadata(
            formatRaw = formatRaw,
            handleId = handleId,
            width = width,
            height = height,
            timestampNs = timestampNs,
            monotonicSeq = seq,
        )

        return mapOf(
            "source" to if (pushed) "native-android-rust" else "native-android",
            "width" to width,
            "height" to height,
            // Vision Camera reports `timestamp` in nanoseconds on Android
            // (System.nanoTime() at frame arrival; matches the iOS PTS
            // contract closely enough for ADR-0003's wrap-safe seq id).
            "timestampNs" to timestampNs,
            "pixelFormat" to frame.pixelFormat.unionValue,
            "orientation" to frame.orientation.unionValue,
            "monotonicSeq" to seq,
            "rustBridgeAvailable" to AVPhoneFrameSinkBridge.isAvailable(),
        )
    }
}
