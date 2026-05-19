//
//  AVPhoneFrameSink.swift
//  AIMVISION phone-capture slice 3b native frame-processor plugin (ADR-0009).
//
//  Receives every camera frame from `react-native-vision-camera`'s worklet
//  runtime, extracts metadata, and returns it as a JS object. Slice 3c
//  additionally hands the frame metadata to the Rust
//  `aimvision-camera-phone` crate via the C ABI media plane defined in
//  ADR-0003 — see `AVPhoneFrameSinkBridge.swift`. The bridge gracefully
//  no-ops when the Rust static library hasn't been linked yet, so the
//  plugin keeps working with metadata-only output on day-zero.
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

        let width = UInt32(frame.width)
        let height = UInt32(frame.height)
        // `frame.timestamp` is the CMSampleBuffer PTS in nanoseconds.
        let timestampNs = UInt64(frame.timestamp)
        let pixelFormatRaw = frame.pixelFormat.rawValue
        let orientationRaw = frame.orientation.rawValue

        // Map Vision Camera's pixel format string to the C ABI enum.
        // Vision Camera doesn't surface NV12 vs I420 reliably across
        // versions; default to NV12 (the iOS default from VideoToolbox)
        // and let the Rust consumer handle reformatting if needed.
        let formatRaw: UInt32 = 0  // AIMVISION_FRAME_FORMAT_NV12

        // The `handle_id` field of the Rust Frame is the IOSurface ID.
        // Vision Camera doesn't expose CMSampleBufferRef → IOSurface from
        // its Frame wrapper at this slice; we ferry the PTS as a stand-in
        // identifier so downstream consumers can still correlate frames.
        // Slice 3c-followup will wire real IOSurface IDs.
        let handleId = timestampNs

        let pushed = AVPhoneFrameSinkBridge.shared.pushFrameMetadata(
            formatRaw: formatRaw,
            handleId: handleId,
            width: width,
            height: height,
            timestampNs: timestampNs,
            monotonicSeq: seq
        )

        return [
            "source": pushed ? "native-ios-rust" : "native-ios",
            "width": frame.width,
            "height": frame.height,
            // `frame.timestamp` on iOS is the CMSampleBuffer PTS in
            // nanoseconds — matches the contract from ADR-0003.
            "timestampNs": frame.timestamp,
            "pixelFormat": pixelFormatRaw,
            "orientation": orientationRaw,
            "monotonicSeq": seq,
            "rustBridgeAvailable": AVPhoneFrameSinkBridge.shared.isAvailable,
        ]
    }
}
