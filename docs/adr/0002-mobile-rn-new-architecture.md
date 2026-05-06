# ADR-0002: Mobile on React Native New Architecture (Hermes + Fabric + JSI + TurboModules)

**Status:** Accepted · **Date:** 2026-05-06 · **Owner:** Software Architect (with Mobile App Builder concurrence)

## Context

The V1 sprint plan specifies React Native as the mobile stack but does not pin which RN architecture, which JS engine, or which interop strategy. This is the single most consequential mobile decision: the legacy async JSON bridge cannot move frame data, and retrofitting JSI/Fabric in Sprint 12 (after the schema and screens have solidified) would be a multi-sprint slip.

The hot path requirements are concrete:

- **24fps live preview** (Hero 13 over Wi-Fi, ~480p; over USB-C UVC, 1080p) decoded natively and overlaid with pose keypoints.
- **Per-frame metadata flow** (timestamps, decoder lag markers, pose tensor handles) at 24+ Hz.
- **Pose keypoint stream** (33 to 133 keypoints depending on model) at 8–12 Hz, rendered on a Skia canvas aligned to the video frame.
- **Audio shot detection** running continuously on a 50 ms hop, firing events that trigger feed entries within 800 ms (per [Performance review](../reviews/10-performance-benchmarker.md)).
- **Background uploads** of 1–2 GB recordings, resumable, constraint-aware.
- **Offline-first storage** of thousands of shots with observable queries driving the feed UI.

The legacy RN bridge (async JSON, batched messages) tops out at roughly 10 MB/s of marshaled data and adds 80–150 ms of round-trip latency — which is the entire RN/Fabric commit budget. The [Software Architect review §3](../reviews/03-software-architect.md) and [Mobile review §1](../reviews/04-mobile-app-builder.md) both flag this as the "silent killer" of the original plan.

## Decision

**RN 0.76+ on the New Architecture from Sprint 3, not retrofitted later.** Specifically:

- **Hermes** as the JS engine. AOT bytecode compilation, smaller heap, faster startup. No JSC.
- **Fabric** as the renderer. Synchronous layout commits keep the Skia overlay aligned to the video frame on the same render pass.
- **JSI (JavaScript Interface)** as the interop substrate. Native objects expose `JSI::HostObject` interfaces consumed directly from JS without serialization.
- **TurboModules** for all native modules from day one. No legacy `NativeModules` shims.
- **Frame data via JSI HostObjects + zero-copy `IOSurface` (iOS) / `AHardwareBuffer` (Android).** The Rust core delivers decoded pixel buffers as opaque handles; Swift/Kotlin wrap them as `CVPixelBuffer` / `HardwareBuffer`; a C++ TurboModule exposes them to JS as a `JSI::ArrayBuffer` view. **No frame data ever traverses the JS heap.**
- **Pose keypoints via Reanimated 3 `SharedValue`.** Keypoints are written by the inference thread directly into a shared memory region; the Reanimated worklet reads them on the UI thread and feeds them to a `@shopify/react-native-skia` canvas. No bridge hop.
- **Reference architecture: `react-native-vision-camera` v4.** Frame processors on a dedicated worklet runtime, pixel buffers as JSI HostObjects, Skia overlays composited via `@shopify/react-native-skia`. We adopt this pattern wholesale and do not invent a new one.
- **Threading model (per [Mobile review §3](../reviews/04-mobile-app-builder.md)):**
  - _Camera I/O thread:_ dedicated single-threaded tokio runtime in Rust, owning BLE + Wi-Fi sockets.
  - _Decode thread:_ `VTDecompressionSession` (iOS) / `MediaCodec` async (Android) writing to a triple-buffered ring of pixel handles.
  - _ML thread:_ Core ML / NNAPI inference on a separate dispatch queue, reads pixel buffer by handle (no copy), writes pose tensor to a lock-free SPSC channel.
  - _UI thread:_ Reanimated worklet reads latest pose tensor via `SharedValue`, Fabric commits Skia overlay.
  - _No `runOnJS` calls in the hot path._
- **Backpressure: drop pose frames first, then YOLO frames; never drop video frames or audio frames.** A stale-keypoints flag lets the overlay reuse the previous skeleton if the inference queue depth exceeds 2.
- **Offline DB: WatermelonDB with the JSI adapter** (`@nozbe/watermelondb` 0.27+ with `JSIAdapter`). SQLite under the hood, observable queries drive the feed UI. Realm is rejected on licensing grounds; expo-sqlite is too low-level for sync.
- **Background uploads via tus.io over S3 multipart**, 5 MB chunks, resumable, with `BGProcessingTaskRequest` (iOS, not `BGAppRefresh`) and `WorkManager` with `setRequiredNetworkType(UNMETERED)` (Android). On-device SHA-256 computed before upload; backend dedupes.
- **Day-one infra in the mobile app:** `@sentry/react-native` (with Hermes stack-trace symbolication and Rust panic-hook integration), Statsig or PostHog feature flags, Expo EAS Update for OTA, `PrivacyInfo.xcprivacy` manifest, accessibility primitives (Dynamic Type, RTL-safe layouts, VoiceOver labels), and a battery/thermal telemetry stream from Sprint 7. Per [Mobile review §Sprint resequencing](../reviews/04-mobile-app-builder.md), these move from Sprints 18–22 to Sprint 3–5.

The legacy RN bridge is **disqualified**. KMM (Kotlin Multiplatform Mobile) is not under consideration — it would replace RN, not coexist with it, and the camera-core Rust crate (ADR-0003) already covers the cross-platform protocol layer.

## Consequences

**Easier:**

- Live preview with overlaid pose hits the [Performance review](../reviews/10-performance-benchmarker.md) end-to-end target of ~1.0–1.5 s on Wi-Fi and <1 s on USB-C.
- Frame buffers never round-trip through the JS heap — RN is no longer the latency bottleneck.
- The same Skia canvas pattern used for live preview also drives post-session playback and coach annotations, giving us one render path to maintain.
- WatermelonDB observable queries make the feed reactive without manual refresh logic; the sync engine (ADR-0006) populates rows and the UI updates.

**Harder:**

- Some popular RN libraries still target the legacy bridge. We accept the constraint and use only Fabric/TurboModule-compatible libraries; we maintain a short list of vetted libraries in `docs/mobile/dependency-policy.md`.
- Debugging is harder than legacy RN (Flipper support is reduced; React Native DevTools is the official path). We accept the cost.
- Engineers unfamiliar with JSI need a ramp; we mitigate with `react-native-vision-camera` and `@shopify/react-native-skia` as worked examples.

**Reversibility:** Low for the architecture choice itself (rolling back to legacy bridge means rewriting the camera-data path), but high for individual components (we can swap WatermelonDB for SQLite-direct if needed). The architecture choice is a Sprint 3 decision precisely because it is hard to undo later.

## Alternatives Considered

1. **Legacy RN bridge with native modules and a custom batching layer.** Rejected. The bridge cannot carry 24fps frame metadata. This is the path the original sprint plan implicitly assumed and is the single biggest "silent killer" called out by the Software Architect and Mobile reviews.
2. **Native iOS (Swift+SwiftUI) and native Android (Kotlin+Compose) — drop RN entirely.** Best performance ceiling. Rejected because the team is small and we cannot maintain two native codebases at the velocity Egypt validation requires. RN with the New Architecture closes most of the gap.
3. **Flutter.** Closer to native performance than legacy RN, single codebase. Rejected because the camera-core Rust crate's `extern "C"` interop is more mature with iOS/Swift and Android/Kotlin than with Flutter's `dart:ffi`, and because the RN ecosystem (Vision Camera, Skia, Reanimated) is more mature for this exact use case.
4. **Capacitor or Cordova webview app.** Rejected on latency grounds — webview frame paths are nowhere near the 41 ms/frame budget.

## References

- [Mobile App Builder review §1–4 and §Things missing](../reviews/04-mobile-app-builder.md) — the complete spec for the New Architecture mobile stack, threading model, zero-copy FFI, and day-one infra.
- [Software Architect review §3 (live frame streaming)](../reviews/03-software-architect.md) — bridge throughput math.
- [Performance review §Live Latency Budget Table](../reviews/10-performance-benchmarker.md) — frame-by-frame budget validation.
- [ADR-0003: Rust camera-core split](0003-rust-camera-core-split.md) — companion ADR; the Rust crate is the producer of pixel handles consumed here.
- React Native New Architecture: <https://reactnative.dev/architecture/landing-page>
- `react-native-vision-camera` v4: <https://react-native-vision-camera.com/>
- `@shopify/react-native-skia`: <https://shopify.github.io/react-native-skia/>
- `@nozbe/watermelondb` JSI adapter: <https://watermelondb.dev/docs/Implementation/Adapters>
