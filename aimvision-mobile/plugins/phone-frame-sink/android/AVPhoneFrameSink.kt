/*
 * AVPhoneFrameSink.kt
 *
 * Android half of the AIMVISION phone-capture slice 3b native plugin
 * (ADR-0009). Mirror of the iOS class in `../ios/AVPhoneFrameSink.swift`.
 *
 * Vision Camera v4 surfaces every camera frame to subclasses of
 * `FrameProcessorPlugin`. The `callback()` runs on the Vision Camera worklet
 * thread; we return a metadata map back to the JS worklet. Slice 3c is
 * where we'll hand the underlying `ImageProxy` to Rust via JNI + the
 * `extern "C"` media plane from ADR-0003.
 *
 * The companion package class `AVPhoneFrameSinkPackage` is what the React
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
        // Slice 3b: metadata only. The slice 3c JNI call into Rust will go
        // here, with frame.imageProxy as the pixel-data source.
        val width: Int = frame.width
        val height: Int = frame.height
        return mapOf(
            "source" to "native-android",
            "width" to width,
            "height" to height,
            // Vision Camera reports `timestamp` in nanoseconds on Android
            // (System.nanoTime() at frame arrival; matches the iOS PTS
            // contract well enough for slice 3b).
            "timestampNs" to frame.timestamp,
            "pixelFormat" to frame.pixelFormat.unionValue,
            "orientation" to frame.orientation.unionValue,
        )
    }
}
