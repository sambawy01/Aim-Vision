//
//  AVPhoneFrameSinkBridge.swift
//  Slice 3c of ADR-0009 — Swift side of the FFI bridge into the Rust
//  `aimvision-camera-phone` crate's C ABI (see
//  ../../../../aimvision-camera-core/crates/aimvision-camera-phone/include/
//  aimvision_camera_phone.h).
//
//  Symbol resolution strategy: dlsym against the main bundle. When the
//  dev has run `cargo build` and bundled the static library into the
//  Xcode target, the C ABI symbols are exported into the main binary,
//  dlsym finds them, and frame pushes start going to Rust. Until then
//  `isAvailable` reports `false` and the plugin's `callback` falls back
//  to the metadata-only path from slice 3b — this keeps the app running
//  without the Rust library on day-zero of integration.
//
//  Why dlsym (not direct linking from Swift):
//  - We want a single source file that compiles whether or not the Rust
//    library is present in the dev's build. Direct extern declarations
//    would fail to link without the library; dlsym defers that to a
//    runtime check we can fall back from.
//  - The performance penalty is paid once at init, not per-frame.

import Foundation

private typealias FFI_New = @convention(c) (
    UnsafePointer<CChar>?, Int, Int
) -> UnsafeMutableRawPointer?
private typealias FFI_Free = @convention(c) (UnsafeMutableRawPointer?) -> Void
private typealias FFI_PushFrame = @convention(c) (
    UnsafeMutableRawPointer?, UInt32, UInt64, UInt32, UInt32, UInt64, UInt64
) -> Bool
private typealias FFI_DroppedFrames = @convention(c) (UnsafeMutableRawPointer?) -> UInt64

/// Singleton FFI bridge to the Rust `PhoneCamera`. The lifecycle is
/// process-lifetime: we never call `_free` because the camera is meant
/// to live as long as the app does. The OS reclaims everything on exit.
@objc(AVPhoneFrameSinkBridge)
public final class AVPhoneFrameSinkBridge: NSObject {
    @objc public static let shared = AVPhoneFrameSinkBridge()

    /// `true` iff the C ABI symbols were resolved at process start AND
    /// the Rust `_new` call returned a non-NULL handle. When false the
    /// plugin must not call `pushFrame`.
    @objc public let isAvailable: Bool

    private let cameraHandle: UnsafeMutableRawPointer?
    private let pushFrame: FFI_PushFrame?
    private let droppedFrames: FFI_DroppedFrames?

    private override init() {
        // dlopen(NULL, ...) returns a handle to the running process — all
        // symbols statically linked into the main binary are visible
        // through it. RTLD_LAZY is fine here; we resolve in init.
        guard let proc = dlopen(nil, RTLD_LAZY) else {
            self.cameraHandle = nil
            self.pushFrame = nil
            self.droppedFrames = nil
            self.isAvailable = false
            super.init()
            return
        }
        defer { dlclose(proc) }

        guard let newSym = dlsym(proc, "aimvision_phone_camera_new"),
              let pushSym = dlsym(proc, "aimvision_phone_camera_push_frame"),
              let droppedSym = dlsym(proc, "aimvision_phone_camera_dropped_frames") else {
            self.cameraHandle = nil
            self.pushFrame = nil
            self.droppedFrames = nil
            self.isAvailable = false
            super.init()
            return
        }

        let newFn = unsafeBitCast(newSym, to: FFI_New.self)
        let pushFn = unsafeBitCast(pushSym, to: FFI_PushFrame.self)
        let droppedFn = unsafeBitCast(droppedSym, to: FFI_DroppedFrames.self)

        // Per-process singleton: capacity 64 frames ≈ 2 s @ 30 fps; 32
        // audio chunks ≈ 320 ms @ 10 ms chunks. Matches the slice-3a
        // tests' default scaling.
        let handle: UnsafeMutableRawPointer? = "phone-0".withCString { ptr in
            newFn(ptr, 64, 32)
        }

        self.cameraHandle = handle
        self.pushFrame = pushFn
        self.droppedFrames = droppedFn
        self.isAvailable = handle != nil
        super.init()
    }

    /// Push one frame to Rust. Returns `true` on a successful push,
    /// `false` if the bridge is unavailable. The bool the C ABI returns
    /// (whether a frame was evicted to make room) is exposed through the
    /// `droppedFramesCount` accessor — eviction is normal under
    /// backpressure and doesn't fail the push.
    @objc public func pushFrameMetadata(
        formatRaw: UInt32,
        handleId: UInt64,
        width: UInt32,
        height: UInt32,
        timestampNs: UInt64,
        monotonicSeq: UInt64
    ) -> Bool {
        guard isAvailable,
              let cameraHandle = cameraHandle,
              let pushFrame = pushFrame else {
            return false
        }
        _ = pushFrame(cameraHandle, formatRaw, handleId, width, height, timestampNs, monotonicSeq)
        return true
    }

    /// Read the Rust-side cumulative dropped-frames counter. Returns 0
    /// when the bridge is unavailable.
    @objc public var droppedFramesCount: UInt64 {
        guard isAvailable,
              let cameraHandle = cameraHandle,
              let droppedFrames = droppedFrames else {
            return 0
        }
        return droppedFrames(cameraHandle)
    }
}
