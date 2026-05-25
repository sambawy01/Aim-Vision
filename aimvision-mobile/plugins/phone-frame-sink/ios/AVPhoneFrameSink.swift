//
//  AVPhoneFrameSink.swift
//  AIMVISION phone-capture slice 3b native frame-processor plugin (ADR-0009).
//
//  Receives every camera frame from `react-native-vision-camera`'s worklet
//  runtime, extracts metadata, and returns it as a JS object. Slice 3c
//  will hand the frame metadata to the Rust `aimvision-camera-phone` crate
//  via the C ABI media plane defined in ADR-0003 (`AVPhoneFrameSinkBridge`
//  to be added then). This slice is metadata-only.
//
//  Why this lives in source control (not a published package):
//  - The plugin's purpose is internal-dev-only per ADR-0009 §17.3.
//  - Co-locating with the app means there's no version-pin drift between the
//    RN-side worklet and the native receiver.
//
//  Why a separate Obj-C category for registration (see AVPhoneFrameSink.m):
//  - Vision Camera's `FrameProcessorPluginRegistry` uses Obj-C `+load`-time
//    registration; Swift doesn't allow class-level `+load`. The category in
//    the .m file is the bridge.
//

import UIKit
import VisionCamera

@objc(AVPhoneFrameSink)
public class AVPhoneFrameSink: FrameProcessorPlugin {
    private static var monotonicSeq: UInt64 = 0

    public override init(proxy: VisionCameraProxyHolder, options: [AnyHashable: Any]! = [:]) {
        super.init(proxy: proxy, options: options)
    }

    public override func callback(_ frame: Frame, withArguments arguments: [AnyHashable: Any]?) -> Any? {
        // Per-camera monotonic sequence: PTS is what we ferry to Rust as
        // the timestamp; this counter is the wrap-safe identifier
        // `(camera_id, monotonic_seq)` from ADR-0003. Single worklet
        // thread → no atomic needed.
        AVPhoneFrameSink.monotonicSeq &+= 1
        let seq = AVPhoneFrameSink.monotonicSeq

        // vision-camera v4+ surfaces `pixelFormat` as a String
        // (e.g. "yuv", "rgb"), not an enum with `rawValue`.
        let pixelFormatRaw: String = frame.pixelFormat

        // `frame.orientation` is `UIImage.Orientation`; serialise to a
        // stable string so the JS side has a stable contract.
        let orientationRaw: String = {
            switch frame.orientation {
            case .up: return "up"
            case .down: return "down"
            case .left: return "left"
            case .right: return "right"
            case .upMirrored: return "upMirrored"
            case .downMirrored: return "downMirrored"
            case .leftMirrored: return "leftMirrored"
            case .rightMirrored: return "rightMirrored"
            @unknown default: return "unknown"
            }
        }()

        return [
            "source": "native-ios",
            "width": frame.width,
            "height": frame.height,
            // `frame.timestamp` on iOS is the CMSampleBuffer PTS in
            // nanoseconds — matches the contract from ADR-0003.
            "timestampNs": frame.timestamp,
            "pixelFormat": pixelFormatRaw,
            "orientation": orientationRaw,
            "monotonicSeq": seq,
            "rustBridgeAvailable": false,
        ]
    }
}
