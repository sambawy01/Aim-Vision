//
//  AVPhoneFrameSink.swift
//  AIMVISION phone-capture slice 3b native frame-processor plugin (ADR-0009).
//
//  Receives every camera frame from `react-native-vision-camera`'s worklet
//  runtime, extracts metadata, and (in slice 3b) returns it as a JS object.
//  Slice 3c will hand the same frame to the Rust `aimvision-camera-phone`
//  crate via the C ABI media plane defined in ADR-0003.
//
//  Why this lives in source control (not a published package):
//  - The plugin's purpose is internal-dev-only per ADR-0009 §17.3; we don't
//    publish it because we don't want any third party shipping with it.
//  - Co-locating with the app means there's no version-pin drift between the
//    RN-side worklet and the native receiver.
//
//  Why a separate Obj-C category for registration (see AVPhoneFrameSink.m):
//  - Vision Camera's `FrameProcessorPluginRegistry` uses Obj-C `+load`-time
//    registration; Swift doesn't allow class-level `+load`. The category in
//    the .m file is the bridge.
//

import VisionCamera

@objc(AVPhoneFrameSink)
public class AVPhoneFrameSink: FrameProcessorPlugin {
    public override init(proxy: VisionCameraProxyHolder, options: [AnyHashable: Any]! = [:]) {
        super.init(proxy: proxy, options: options)
    }

    public override func callback(_ frame: Frame, withArguments arguments: [AnyHashable: Any]?) -> Any? {
        // Slice 3b just surfaces metadata. We deliberately don't touch the
        // CMSampleBuffer's pixel data — slice 3c is where we cross into Rust
        // via the C ABI, and that's the only place we want to handle raw
        // pixel ownership. Until then we report what we can read cheaply.
        return [
            "source": "native-ios",
            "width": frame.width,
            "height": frame.height,
            // `frame.timestamp` on iOS is the CMSampleBuffer PTS in
            // nanoseconds — matches the contract from ADR-0003.
            "timestampNs": frame.timestamp,
            "pixelFormat": frame.pixelFormat.rawValue,
            "orientation": frame.orientation.rawValue,
        ]
    }
}
