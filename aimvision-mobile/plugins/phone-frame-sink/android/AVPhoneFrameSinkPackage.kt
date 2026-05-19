/*
 * AVPhoneFrameSinkPackage.kt
 *
 * Vision Camera v4 frame-processor-plugin registration for Android. This
 * package class auto-runs at app startup (registered into MainApplication
 * by the Expo config plugin in
 * `plugins/phone-frame-sink/withPhoneFrameSink.ts`) and adds the
 * `avPhoneFrameSink` plugin to the global frame processor registry, where
 * `VisionCameraProxy.initFrameProcessorPlugin('avPhoneFrameSink')` finds
 * it from the JS worklet.
 *
 * The 1:1 name match with the iOS plugin (`@"avPhoneFrameSink"` in
 * AVPhoneFrameSink.m) is what lets a single JS worklet call resolve to
 * the right native code on both platforms.
 */

package com.aimvision.app.phoneframesink

import com.facebook.react.ReactPackage
import com.facebook.react.bridge.NativeModule
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.uimanager.ViewManager
import com.mrousavy.camera.frameprocessors.FrameProcessorPluginRegistry

class AVPhoneFrameSinkPackage : ReactPackage {
    init {
        FrameProcessorPluginRegistry.addFrameProcessorPlugin("avPhoneFrameSink") { proxy, options ->
            AVPhoneFrameSink(proxy, options)
        }
    }

    override fun createNativeModules(reactContext: ReactApplicationContext): List<NativeModule> = emptyList()

    override fun createViewManagers(reactContext: ReactApplicationContext): List<ViewManager<*, *>> = emptyList()
}
