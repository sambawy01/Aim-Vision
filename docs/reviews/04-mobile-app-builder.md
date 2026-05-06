# AIMVISION Mobile Architecture Critique

**Reviewer:** Mobile App Builder · **Date:** 2026-05-06 · **Source:** `AIMVISION_V1_Sprint_Build_Plan.txt` v1.0

## Critical mobile architecture decisions (4)

**1. JSI/Fabric is mandatory for the frame path; the old bridge is disqualifying.** The async JSON bridge will collapse under 24fps of 1080p frame metadata plus pose keypoints. Specify Hermes + the New Architecture (RN 0.76+) from Sprint 3, not retrofitted later. The hot path: Rust core delivers decoded frames to a C++ TurboModule (HostObject) that exposes a `JSI::ArrayBuffer` view over native memory; pose keypoints flow through a SharedValue (Reanimated 3) to a Skia canvas on the UI thread. **Reference architecture: react-native-vision-camera v4** — frame processors run on a dedicated worklet runtime, pixel buffers are exposed as JSI HostObjects, and Skia overlays composite via `@shopify/react-native-skia`. Adopt that pattern wholesale; do not invent a new one. Fabric is required for the synchronous layout commits that keep overlay aligned to video.

**2. UniFFI is the right call, but pin the toolchain and accept its limits.** UniFFI (Mozilla, used in production by Firefox sync, Matrix Rust SDK, Bitwarden, Signal-rs ports) handles structs, enums, async, traits, and callbacks; what it does _not_ do well is zero-copy buffer sharing or callback-heavy hot loops. Use UniFFI for the control plane (pairing, settings, session lifecycle, error taxonomy) and hand-write a thin C ABI (`#[no_mangle] extern "C"`) for the frame data path consumed by Swift via a bridging header and Kotlin via JNI directly. Pin `uniffi-rs` to a specific minor version — the proc-macro UDL changed twice in 2024–2025 and will break iOS/Android bindings simultaneously if you float it. Battle-tested crates: `matrix-rust-sdk`, `bitwarden-sdk`, `glean-core`, `nimbus-fml`. Avoid `uniffi-bindgen-cpp` (immature).

**3. Threading model — three queues, no `runOnJS` in the hot path.**

- _Camera I/O thread:_ dedicated tokio runtime in Rust (single-threaded, pinned), owning BLE + Wi-Fi sockets. Do not let Swift/Kotlin touch the GoPro socket.
- _Decode thread:_ hardware decoder callback (VideoToolbox `VTDecompressionSession` on iOS, `MediaCodec` async mode on Android) writes into a ring buffer of `CVPixelBuffer` / `AHardwareBuffer`.
- _ML thread:_ Core ML / NNAPI inference on a separate dispatch queue, reads pixel buffer by handle (no copy), writes pose tensor to a lock-free SPSC channel.
- _UI thread (RN UI / Skia):_ reads latest pose tensor via JSI SharedValue and composites. Use a triple buffer; never block.

**4. Zero-copy across FFI.** Frames must never round-trip through JS heap. iOS: pass `IOSurface` IDs (uint32) across the FFI; Swift wraps as `CVPixelBuffer` and feeds the Skia `SkImage::MakeFromTexture`. Android: pass `AHardwareBuffer` via `HardwareBuffer` (API 26+) → `SurfaceTexture` → Skia GL backend. Rust core gets only an opaque handle + width/height/format; it never touches pixels for live preview (decode lives natively for hardware-accel access). ML inference reads the same buffer via `MLMultiArray`/`TensorImage` zero-copy adaptors.

## Live preview latency budget (1-3s target, 24fps = 41ms/frame)

| Stage                                     | Budget        | Notes                                                                                                                             |
| ----------------------------------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Hero 13 encode + Wi-Fi RTSP/UDP           | 400-900ms     | Dominant; GoPro preview stream is ~0.5–1s baked-in. Use the low-latency preview endpoint (port 8554), not the recorded MP4 chunks |
| Jitter buffer                             | 100ms         | Tunable; trade against stutter                                                                                                    |
| H.264 hardware decode                     | 8-15ms        | VideoToolbox / MediaCodec async; **never software**                                                                               |
| Pose inference (MediaPipe BlazePose Lite) | 15-25ms       | Core ML on ANE / NNAPI on Hexagon                                                                                                 |
| Skia overlay composite                    | 4-8ms         | GPU; 60fps headroom                                                                                                               |
| RN/Fabric commit                          | 4-10ms        | Worklet, no bridge hop                                                                                                            |
| **End-to-end**                            | **~1.0-1.5s** | Within target; Wi-Fi is the variance source                                                                                       |

Backpressure: drop pose frames, never video frames. If ML queue depth >2, skip inference for that frame and reuse the previous keypoints with a `staleness` flag — the eye won't see 12fps overlays on 24fps video.

## Offline-first specifics (3)

**5. WatermelonDB, not Realm or expo-sqlite.** For 1000s of shots/athlete with blob refs, lazy loading, and observable queries that drive the feed UI, WatermelonDB beats both: SQLite under the hood, async/observable on top, JSI adapter (`@nozbe/watermelondb` 0.27+ with `JSIAdapter`). Realm's licensing is hostile post-MongoDB acquisition; expo-sqlite is too low-level for sync. Schema: `sessions`, `shots`, `annotations`, `recordings(local_uri, remote_uri, upload_state, sha256)`, `sync_log`.

**6. Sync engine — hybrid LWW + per-field vector clocks for annotations.** Shot detections are immutable facts (LWW by `(device_id, timestamp_ns)` is fine). Annotations from coach + athlete simultaneously need CRDT semantics — use Automerge 2.0 (Rust-native, embeds cleanly in the shared core via UniFFI; the Matrix team uses it) for the `annotations` document only. Don't CRDT the whole DB; that's overkill and expensive.

**7. Background upload — resumable, chunked, constraint-aware.** iOS: `URLSession` background config with `BGProcessingTaskRequest` (not `BGAppRefresh`; it's too short). Android: `WorkManager` with `setRequiredNetworkType(UNMETERED)` + `setRequiresCharging(true)` defaults, user-overridable. Files: tus.io protocol over S3 multipart (5MB chunks, resumable on partial failure, idempotent via `Upload-Metadata`). Compute SHA-256 on-device before upload; backend dedupes. A 10-minute 4K clip at ~1.5GB needs all of this.

## Things missing from the plan (7)

1. **Sentry/Crashlytics from Sprint 3, not Sprint 22.** Egypt validation in Sprint 19 without crash telemetry is flying blind. Add `@sentry/react-native` + native crash reporting (Sentry covers RN JS, Hermes stack traces, native iOS/Android, and Rust via `sentry-rust` panic hook) day one.
2. **OTA updates via Expo EAS Update** (or CodePush — but Microsoft is sunsetting CodePush 2025). Egypt is in-country; you cannot wait 2-7 days for App Store review on a hotfix. Critical from Sprint 5.
3. **Feature flags from Sprint 3** — Statsig, PostHog, or self-hosted Unleash. Required to dark-launch the diagnostic classifier and A/B coach-mode tone variations without redeploying.
4. **PrivacyInfo.xcprivacy manifest (iOS 17+).** Mandatory since May 2024; missing = automatic rejection. Add to Sprint 4 alongside the iOS native module bringup. Declare API reasons for `UserDefaults`, `FileTimestamp`, `SystemBootTime`, `DiskSpace`.
5. **Device farm coverage** — Firebase Test Lab (Android, free tier) + AWS Device Farm or BrowserStack App Live (iOS). Pixel 6a, Galaxy A-series, iPhone 12/13 (the median shooter device, not your team's iPhone 16 Pro).
6. **Accessibility from Sprint 3, not Sprint 18.** Older shooters have presbyopia and tremor — minimum 17pt Dynamic Type, 44pt tap targets, VoiceOver labels on the live feed. Retrofitting in Sprint 18 means redoing every component.
7. **Battery/thermal budget defined in Sprint 3.** Target: <12% battery/hour on iPhone 13, no thermal state above `.serious` (`ProcessInfo.thermalState`). Continuous Wi-Fi AP mode + BLE + ANE + screen-on is brutal; budget enforces architecture choices (e.g., ANE not GPU for ML, drop GPS to 1Hz, disable preview when phone is pocketed via proximity sensor).

## Sprint resequencing (5)

- **Move Crashlytics/Sentry, feature flags, OTA, PrivacyInfo, and battery instrumentation from Sprints 19/22 → Sprint 3-4.** Non-negotiable infra.
- **Move "older device lite-model variants" from Sprint 20 [P1] → Sprint 9 [P0].** Quantization (INT8 via Core ML Tools `cto.coreml.optimize`, NNAPI's `ANEURALNETWORKS_TENSOR_QUANT8_ASYMM`) is a model-architecture decision, not a polish step. Train the lite variant in parallel with the full one.
- **Move App Store firearms positioning from Sprint 22 → Sprint 1.** File a TestFlight build with neutral metadata (positioning: "Olympic shooting sports analytics", "ISSF training", screenshots showing pose skeletons + charts, no shotguns visible) by Sprint 6 to surface rejection signals 12 sprints early. ShotKam ships as "trap/skeet camera"; MantisX ships as "shooting performance"; copy that exact tone. Preserve the PWA fallback (Sprint 1 web shell) as a real deployment target, not a hypothetical.
- **Move offline-first DB + sync engine from Sprint 12 → Sprint 5.** It's a foundational data-model decision; bolting it on after the schema solidifies forces a rewrite.
- **Move accessibility + i18n scaffolding from Sprint 18 → Sprint 3** (strings extraction, RTL-safe layout primitives, dynamic type). Arabic RTL retrofitted in Sprint 18 is a 2-sprint slip risk.
