# AIMVISION Mobile Architecture Specification

**Status:** Canonical · **Version:** 1.0 · **Date:** 2026-05-06
**Owners:** Mobile platform leads (iOS, Android, Rust core)
**Inputs:** `docs/reviews/04-mobile-app-builder.md` (primary), `docs/reviews/03-software-architect.md`, `docs/reviews/05-embedded-firmware-engineer.md`, `docs/reviews/10-performance-benchmarker.md`
**Scope:** AIMVISION clay shooting coaching app — React Native shell, Rust core (`aimvision-core`), GoPro Hero 13 Wi-Fi/USB-C transports, on-device ML, offline-first sync.

This document is binding. Deviations require an ADR and sign-off from a mobile platform lead. Where the V1 plan and the reviewers disagree, the reviewers win and this spec records the resolution.

---

## 1. Stack

React Native 0.76+ with the New Architecture enabled from Sprint 3 (not retrofitted later, per `04-mobile-app-builder.md` §1). Bridge mode is disqualifying for the live frame path — see `03-software-architect.md` §"Live frame streaming" (RN old bridge ~10 MB/s; 1080p30 RGBA is ~180 MB/s).

**Runtime:**

- **Hermes** — required for Fabric/JSI; no JSC fallback.
- **Fabric** — synchronous layout commits keep the Skia overlay aligned to video; without it, overlay drift on rapid pans is unfixable.
- **JSI** — direct C++ ↔ JS, no serialization; substrate for zero-copy frame handles and Reanimated SharedValues.
- **TurboModules** — replaces all NativeModules; pose streaming, camera control, settings, lifecycle codegenned from `.ts` specs.
- **Reanimated 3** — worklet runtime for the overlay pipeline; pose tensor → SharedValue → Skia worklet at vsync.
- **`@shopify/react-native-skia`** — GPU canvas for the live overlay (pose skeleton + barrel box + reticle).

**Reference architecture:** `react-native-vision-camera` v4 (≥ 4.5). Adopt its pattern wholesale — frame processors on a dedicated worklet runtime, pixel buffers as JSI HostObjects, Skia overlays via `@shopify/react-native-skia`, JS thread never sees pixels. Our internal `react-native-aimvision-camera` consumes GoPro frames through the same Frame interface, so worklet ergonomics carry over. Do not invent a new pattern.

**Version pins (Sprint 3 freeze):** `react-native@0.76.x` (bump only on minor + full QA), `react-native-reanimated@3.16.x`, `@shopify/react-native-skia@1.5.x`, `react-native-mmkv@3.x`, `@nozbe/watermelondb@0.27.x`, `@sentry/react-native@5.x`. TypeScript strict mode non-optional — all TurboModule specs round-trip through `react-native-codegen` with no `any` escapes.

---

## 2. Native Module Architecture

The Rust core (`aimvision-core`) exposes **two distinct FFI surfaces**, by design. This is the single most important architectural call in the mobile stack and matches `04-mobile-app-builder.md` §2 verbatim.

### 2a. Control plane — UniFFI

UniFFI handles the control plane: pairing, settings, session lifecycle, error taxonomy, recordings list, hilight tagging, calibration data, sync orchestration. These are structured calls — handfuls of bytes, async-friendly, callback-heavy in the trait sense — exactly what UniFFI's macro-driven code generator does well.

**Why UniFFI:** battle-tested production users — `matrix-rust-sdk` (Element iOS/Android), `bitwarden-sdk`, `glean-core` (every Firefox client), `nimbus-fml`. If UniFFI breaks, half the secure-messaging industry breaks with us. One source of truth (`.udl` or `#[uniffi::export]`) generates Swift + Kotlin; `async fn` lifts to Swift `async`/Kotlin `suspend`; `thiserror` enums lift to typed Swift `Error` and Kotlin sealed classes.

**What UniFFI does _not_ do:** zero-copy buffer sharing (everything copies as `Vec<u8>` or boxed handle); callback-heavy hot loops (each marshals through a dispatch); anything at 24 fps × pixel buffers. We will not ask it to.

**Toolchain pinning (mandatory):** the proc-macro UDL surface changed twice in 2024–2025; floating the version will break iOS and Android bindings simultaneously and leave us debugging codegen across two platforms during a sprint demo. We pin:

```toml
# aimvision-core/Cargo.toml
[dependencies]
uniffi = { version = "=0.28.3", features = ["tokio"] }

[build-dependencies]
uniffi = { version = "=0.28.3", features = ["build"] }
```

The `=` is exact, not caret. Bumps require an ADR and a re-test of every UniFFI-bound API on both platforms. We do **not** use `uniffi-bindgen-cpp` — it is immature and we do not need it; the C++ TurboModule surface is hand-written for reasons described below.

### 2b. Data plane — hand-written C ABI

Frames, audio chunks, and any zero-copy buffer cross a separate, hand-written `extern "C"` surface defined in `aimvision-core/src/ffi.rs`:

```rust
#[no_mangle]
pub extern "C" fn aimv_session_attach_ios_surface(
    session: *mut Session,
    iosurface_id: u32,
    width: u32,
    height: u32,
    format: PixelFormat,
    pts_ns: u64,
) -> StatusCode { /* ... */ }

#[no_mangle]
pub extern "C" fn aimv_session_attach_ahardware_buffer(
    session: *mut Session,
    buffer: *mut std::ffi::c_void, // AHardwareBuffer*
    pts_ns: u64,
) -> StatusCode { /* ... */ }
```

iOS consumes via a bridging header (`aimvision-core.h`, generated by `cbindgen` and committed); Android consumes directly via JNI in a small Kotlin wrapper. No UniFFI on this path. The reasoning is that UniFFI assumes a marshalable function call; an `IOSurface` ID or `AHardwareBuffer` handle is opaque to UniFFI's type system and would be force-fit into a `Vec<u8>` copy.

**Cargo workspace:** `aimvision-core/crates/{core, transport-gopro, ml-bridge, sync, ffi (uniffi), ffi-c (extern "C")}` — control plane via UniFFI, data plane via hand-written C ABI, business logic / GoPro transport / ML control / sync engine isolated.

**Battle-tested UniFFI references:** `matrix-rust-sdk` (async session lifecycle, callback-driven sync); `bitwarden-sdk` (credential types crossing FFI); `glean-core` (telemetry pipelines surviving process death); `nimbus-fml` (feature flag manifest — informs our `ConfigBundle` shape). We do **not** use `uniffi-bindgen-cpp` (immature, and we don't need C++).

---

## 3. Threading Model

Four queues, hard-separated, with explicit handoff primitives. **No `runOnJS` calls in any hot path.** The JS thread is for navigation, layout, and async control flow only; it never sees a pixel and rarely sees a pose tensor (only when the session is paused for review).

| Queue          | Owner                                        | Concurrency primitive                                                                                                                                                 | Responsibilities                                                                                                                      |
| -------------- | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| **Camera I/O** | Rust core                                    | Dedicated `tokio::runtime::Builder::new_current_thread()` runtime, pinned to one OS thread via `core_affinity`                                                        | BLE GATT (CoreBluetooth/Android BluetoothLeScanner under JNI), Wi-Fi UDP/RTP socket, GoPro HTTP/1.1 client, USB-C UVC (where present) |
| **Decode**     | Native (Swift/Kotlin)                        | iOS: `VTDecompressionSession` callback queue (`DispatchQueue` with `.userInteractive` QoS). Android: `MediaCodec` async mode `Handler` on a dedicated `HandlerThread` | H.264 hardware decode, write into ring of `CVPixelBuffer` (iOS) or `AHardwareBuffer` (Android)                                        |
| **ML**         | Native (Swift/Kotlin)                        | iOS: `DispatchQueue(label: "aimv.ml", qos: .userInitiated)`. Android: a dedicated `Handler`/`Executor` for Core ML / NNAPI                                            | Audio shot detector (continuous), pose, barrel YOLO, diagnostic classifier (per-shot). Reads pixel buffer **by handle** — no copy.    |
| **UI / Skia**  | RN UI thread (Fabric) + Skia worklet runtime | Reanimated 3 worklet runtime on the UI thread; Skia composites at vsync                                                                                               | Reads latest pose tensor via JSI SharedValue; composites overlay; never blocks more than one frame.                                   |

**Exact APIs:**

- **iOS decode:** `VTDecompressionSession` with output callback on the Decode queue; format description from SPS/PPS extracted on the Rust side; output `CVPixelBuffer` with `kCVPixelBufferIOSurfacePropertiesKey` (so we get an `IOSurface` to hand across FFI).
- **Android decode:** `MediaCodec.configure(..., flags=0)` in async mode (`setCallback`), output `Surface` → `ImageReader` with `HardwareBuffer.USAGE_GPU_SAMPLED_IMAGE | USAGE_CPU_READ_RARELY`. `minSdk=26` (AHardwareBuffer); Skia GL backend gated on API 26+.
- **iOS ML:** Core ML with `MLModelConfiguration().computeUnits = .cpuAndNeuralEngine` — GPU excluded on iOS for battery (§10).
- **Android ML:** NNAPI delegate on Pixel (Tensor/Edge TPU); QNN-HTP delegate on Snapdragon (Hexagon); ONNX Runtime Mobile builds both. Each on its own dispatch queue, never on decode.

**Handoff primitives:**

- **Decode → ML:** lock-free SPSC ring buffer (size 3) of `{handle, pts_ns, width, height, format}`. `crossbeam::queue::ArrayQueue` in Rust; iOS/Android wrappers above.
- **ML → UI:** triple-buffer of `PoseFrame { keypoints: [(f32, f32, f32); 33], pts_ns, model_version, staleness }`. Non-blocking; readers see the latest committed tensor; Reanimated SharedValue maps to the read slot.
- **UI commit:** Fabric synchronous layout at vsync; Skia composite reads SharedValue via JSI inside the worklet runtime. **No `runOnJS` on the hot path** — only acceptable for "user paused review" flows where 100 ms is fine.

**Backpressure rules (binding):** (1) ML queue depth ≥ 2 → skip pose, reuse previous keypoints with `staleness = 1` (eye does not see 12 fps overlays on 24 fps video); (2) ML queue depth ≥ 3 for >500 ms → drop YOLO entirely, keep audio + pose; (3) **never drop video frames** — overlay can be wrong, a black preview cannot; (4) **never drop audio chunks** — audio fires the shot event. Drop counters export as Sentry breadcrumbs and OTLP metrics (`aimv.pipeline.drops{stage}`).

---

## 4. Zero-Copy Frame Pipeline

Frames never enter the JS heap, are never serialized, and never traverse UniFFI. The core hands out an opaque buffer **handle** + geometry; the native side maps that to a GPU-resident texture feeding both Skia composite and ML inference.

### iOS and Android data paths (side by side)

| Stage               | iOS                                                                                                             | Android                                                                                                                       |
| ------------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Transport ingest    | Rust core (tokio) parses GoPro UDP/RTP MPEG-TS, recovers H.264 NALU stream; USB-C UVC variant on the same crate | Identical Rust core, same crate                                                                                               |
| Hardware decode     | `VTDecompressionSession`, output `CVPixelBuffer` with `kCVPixelBufferIOSurfacePropertiesKey`                    | `MediaCodec` (async mode), output `Surface` to `ImageReader` with `HardwareBuffer.USAGE_GPU_SAMPLED_IMAGE`                    |
| Handle to Rust      | `IOSurfaceID` (uint32) via `aimv_session_attach_ios_surface`                                                    | `AHardwareBuffer*` via `aimv_session_attach_ahardware_buffer` (API 26+)                                                       |
| GPU wrap (overlay)  | `CVMetalTextureCacheCreateTextureFromImage` → `MTLTexture` → `SkImage::MakeFromTexture` (Skia/Metal)            | `EGLImageKHR` from `AHardwareBuffer` → `SurfaceTexture` → Skia/GL backend                                                     |
| ML wrap (zero-copy) | `MLMultiArray.init(pixelBuffer:)` (NV12 → RGB via vImage on ANE-prep); Core ML on ANE                           | `ANeuralNetworksMemory_createFromAHardwareBuffer` (NNAPI) or `QnnTensor` w/ `QNN_HTP_BACKEND_BUFFER_TYPE_DMABUF` (Snapdragon) |
| Compose             | Skia GPU canvas → Fabric commit                                                                                 | Skia GL canvas → Fabric commit                                                                                                |
| Keypoints out       | Pose tensor → SharedValue (Reanimated 3)                                                                        | Pose tensor → SharedValue (Reanimated 3)                                                                                      |

Both paths share the property that **the same buffer feeds Skia and ML**. No copy, no JS heap, no UniFFI marshaling. Skia/Vulkan on Android stays off the table until `react-native-skia`'s Vulkan story stabilizes; we ship Skia/GL.

### What does Rust touch?

**Nothing pixel-shaped, for live preview.** The Rust core sees an opaque handle, dimensions, format, and PTS. It logs, sequences, fans out to ML triggers, but it does not memcpy a frame. Decode lives natively because hardware-accel access is platform-specific and porting VideoToolbox/MediaCodec into Rust would be 6 months of work for zero benefit. This matches `04-mobile-app-builder.md` §4 exactly.

For the **post-session pipeline** (§ post-session in Performance review), Rust does touch frames — but that runs after the session, off the hot path, on the backend, and frames come from S3.

---

## 5. Live Preview Latency Budget

Restated from `10-performance-benchmarker.md` and `04-mobile-app-builder.md`. The realistic p50 on Wi-Fi is **1.0–1.5 s glass-to-glass**; the SLA is **p50 ≤ 2.5 s, p95 ≤ 4 s on Wi-Fi; p50 ≤ 1.2 s on USB-C**.

| Stage                                | Budget             | Notes                                                                                                                                                                                                                                                                                  |
| ------------------------------------ | ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Hero 13 encode + Wi-Fi RTSP/UDP emit | 400–900 ms         | Dominant. GoPro preview stream has ~0.5–1 s baked-in latency. Use the low-latency preview endpoint (UDP port 8554), **not** the recorded MP4 chunks. Hero 11/12 measured 800–1500 ms; Hero 13 unverified (`05-embedded-firmware-engineer.md`), assume similar floor until benchmarked. |
| Jitter buffer                        | 100 ms             | Tunable. Trade against stutter; we start at 100 ms and adapt.                                                                                                                                                                                                                          |
| H.264 hardware decode                | 8–15 ms            | VideoToolbox (iOS) / MediaCodec async (Android). **Never software.** Software decode burns ~35 %+/hr battery and pegs CPU.                                                                                                                                                             |
| Pose inference (RTMPose Lite, NPU)   | 15–25 ms           | Core ML on ANE / NNAPI on Hexagon. See §6 for model choice rationale (RTMPose Lite, **switched from BlazePose** per AI review).                                                                                                                                                        |
| Skia overlay composite               | 4–8 ms             | GPU. 60 fps headroom.                                                                                                                                                                                                                                                                  |
| RN/Fabric commit                     | 4–10 ms            | Worklet, no bridge hop.                                                                                                                                                                                                                                                                |
| **End-to-end (Wi-Fi)**               | **~1.0–1.5 s p50** | Within 2.5 s SLA; Wi-Fi is the variance source.                                                                                                                                                                                                                                        |
| **End-to-end (USB-C UVC)**           | **100–200 ms p50** | Federation-tier path. Cite `10-performance-benchmarker.md` §USB-C; this is the only credible path to <1 s.                                                                                                                                                                             |

**Backpressure:** drop pose first, never video. If the pose queue depth exceeds 2 frames, skip inference and reuse previous keypoints with a `staleness` flag. Drop YOLO before pose. Never drop audio or video. Drop counters surface in the dev-build debug overlay (Sprint 7) and in production telemetry as histograms.

**USB-C path is P0 for federation tier**, not P1. The Mobile and Performance reviewers concur. Without it the federation latency story is not credible.

---

## 6. On-Device ML Targets

Models target the Apple Neural Engine on iOS and Hexagon DSP (Snapdragon QNN-HTP) or Tensor TPU (Pixel) on Android. CPU inference is non-viable for battery (see §10).

### Per-model framework + quantization

| Model                                                          | iOS framework                     | Android framework                                                  | Quantization                                                                                                                                  | Notes                                                                                                                                                |
| -------------------------------------------------------------- | --------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Audio shot detector (CRNN / YAMNet-tiny)                       | Core ML on ANE (`.mlmodelc`)      | NNAPI / TFLite XNNPACK fallback                                    | INT8 via Core ML Tools `cto.coreml.optimize` (post-training); TFLite `optimization_types=[Optimize.DEFAULT]` with INT8 representative dataset | Continuous, 50 ms hop / 200 ms window, never dropped                                                                                                 |
| Pose (**RTMPose Lite**, switched from BlazePose per AI review) | Core ML on ANE                    | NNAPI / QNN-HTP (Snapdragon), TFLite NNAPI delegate (Pixel Tensor) | INT8 ANE; INT8 NNAPI tensor (`ANEURALNETWORKS_TENSOR_QUANT8_ASYMM`)                                                                           | 10 fps subsampled from 24. **Lite variant trained in parallel from Sprint 9, not Sprint 20** — quantization is an architecture decision, not polish. |
| Barrel YOLO (YOLOv8n int8)                                     | Core ML on ANE                    | NNAPI / QNN-HTP                                                    | INT8                                                                                                                                          | 6 fps. First to drop under thermal pressure.                                                                                                         |
| Diagnostic (MLP over engineered features, ~30 dims)            | Core ML on ANE or CPU (it's tiny) | NNAPI or CPU                                                       | FP16 (size doesn't matter)                                                                                                                    | Per-shot only; triggered by the audio detector.                                                                                                      |

### Per-device baselines (p95 latency, INT8, post-quantization)

| Model               | iPhone 13 (ANE) | Pixel 6a (NNAPI / Tensor) | Galaxy S22 (QNN-HTP / Hexagon) |
| ------------------- | --------------- | ------------------------- | ------------------------------ |
| Audio shot detector | 25 ms           | 45 ms                     | 30 ms                          |
| Pose (RTMPose Lite) | 18 ms           | 55 ms                     | 25 ms                          |
| Barrel YOLOv8n int8 | 35 ms           | 90 ms                     | 50 ms                          |
| Diagnostic MLP      | < 5 ms          | < 10 ms                   | < 5 ms                         |

iPhone 13 is the **median shooter device**, not iPhone 16 Pro. Pixel 6a is the budget Android floor we ship to. Galaxy S22 is the Snapdragon flagship reference. Anything below these baselines (e.g., Pixel 4a, iPhone 11) gets the **lite variant** automatically via a runtime device-tier check at session start.

**RTMPose Lite over BlazePose:** per AI review, BlazePose Lite's shoulder/wrist accuracy during fast gun swing is insufficient for our diagnostic feature set. RTMPose-Lite (MMPose) gives ~3 px better keypoint stability at the relevant body points and exports cleanly to Core ML and ONNX. We pay ~5 ms p50 and gain the accuracy floor.

### Quantization strategy

- **iOS:** `coremltools` 7.x with `cto.coreml.optimize.linear_quantize_weights(mode='linear_symmetric', dtype=np.int8)`. Calibration set: 1000 representative frames from internal range fixtures, balanced across lighting conditions. Post-quantization F1 must be within 1.5 % of FP16 on the holdout set or we don't ship.
- **Android (NNAPI):** TFLite converter with `tf.lite.Optimize.DEFAULT` + `representative_dataset_gen` + target spec `[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]`, output type `tf.int8`. NNAPI delegate enabled at runtime; falls back to GPU delegate on devices that don't support `ANEURALNETWORKS_TENSOR_QUANT8_ASYMM` for the op set.
- **Android (QNN-HTP):** `qnn-onnx-converter` with HTP backend; INT8 fixed-point with per-channel weights.

**Lite variant pipeline (Sprint 9, not Sprint 20):** per `04-mobile-app-builder.md` §"Sprint resequencing", trained in parallel from Sprint 9. RTMPose-Tiny (MobileNetV3 backbone) for Pixel 4a / iPhone 11 / older budget tier; YOLOv8n at 320 × 320 input (vs. 640 × 640) gated by device tier; diagnostic is already small. Device-tier selection at session start via `Device.modelIdentifier` / `Build.MODEL`; bundles ship via EAS Update with download-on-first-session.

---

## 7. Offline-First Database

**WatermelonDB with the `JSIAdapter`.** Not Realm (licensing post-MongoDB acquisition is hostile and the app is not a strategic Realm install), not bare `expo-sqlite` (too low-level for our sync semantics and observable queries). WatermelonDB sits on SQLite, exposes async observable queries to React, and the JSI adapter avoids the bridge for reads in lists.

Pinned: `@nozbe/watermelondb@0.27.x` with `JSIAdapter`, SQLite via `react-native-quick-sqlite` (or the bundled JSI adapter back-end depending on platform support at the time of pinning). All cross-platform, both iOS and Android.

### Schema (binding for Sprint 5)

```ts
sessions     { id (uuid v7), athlete_id, club_id, discipline, started_at, ended_at,
               device_id, conditions, monotonic_seq_offset }
shots        { id (uuid v7), session_id, monotonic_seq, device_clock_ns,
               server_clock_ns, detected_via, station, diagnosis_id }   // immutable
annotations  { id, shot_id, automerge_doc (blob), updated_at }          // CRDT, §8
recordings   { id, session_id, local_uri, remote_uri, upload_state, sha256,
               bytes_total, bytes_uploaded, tus_upload_url,
               camera_clock_offset_ms }
sync_log     { id, table, record_id, op, device_id, monotonic_seq, synced_at }
voice_notes  { id, parent_type, parent_id, local_uri, remote_uri,
               duration_ms, transcript, upload_state }
calibrations { id, session_id, camera_serial, intrinsics_json, extrinsics_json,
               charuco_reproj_error_px, captured_at }
```

`upload_state` is a sealed enum (`pending | uploading | paused | complete | failed | orphaned`); `detected_via` is `audio | audio+video | manual`; `monotonic_seq` is strictly increasing per `(session, device)`. The schema explicitly carries `camera_clock_offset_ms` per recording (per Embedded Firmware review §"Multi-Camera Sync"), so multi-cam drift compensation isn't a Sprint 17 retrofit.

**Why WatermelonDB:** async observable queries drive the live feed; lazy loading at 50 shots/page; JSI adapter avoids bridge marshaling on long lists (measurable 8–10 fps gain on Pixel 6a vs. bridge variant); SQLite escape hatch for migrations and reports; `synchronize()` API hooks straight into our sync engine (§8). We do **not** use Realm (licensing risk post-MongoDB Atlas Device Sync deprecation; proprietary file format complicates support) or bare `expo-sqlite` (forces hand-rolled observables and sync state machine).

---

## 8. Sync Engine

**Hybrid: Last-Write-Wins (LWW) for immutable facts, Automerge 2.0 (CRDT) for annotations only.** Per `04-mobile-app-builder.md` §6 and ADR-0006 (event sourcing for shot events).

### Immutable facts → LWW

`sessions`, `shots`, `recordings` (state machine), `voice_notes`, `calibrations` are append-only or have monotonic state machines. LWW keyed on `(device_id, monotonic_seq)` is sufficient. Conflicts on these tables are nearly impossible by construction — a shot is detected by exactly one device's audio detector, and the device that detected it owns the canonical row.

Per ADR-0006, shot events are immutable facts with `(session_id, monotonic_seq, device_clock, server_clock)`. The post-session report is a projection rebuilt server-side. Sync becomes "stream new events with `monotonic_seq > last_cursor`" — no merge conflicts, replayable, audit-ready.

### Mutable shared state → Automerge 2.0

Coach + athlete editing the same annotation simultaneously needs CRDT semantics. We use **Automerge 2.0** (Rust-native, embeds cleanly via UniFFI) for the `annotations.automerge_doc` blob only. The Matrix team uses Automerge in production for similar concurrent-edit needs.

Rationale for not CRDT-ing the whole DB: Automerge documents grow unboundedly with edit history (without compaction); CRDTing immutable shot rows is wasteful, and conflict resolution is a non-problem there. Scope CRDT precisely to where it earns its keep.

### Sync cursor per device

Each device tracks `(table, last_seen_monotonic_seq)` per peer. On reconnect:

1. Pull: `GET /sync?since=<cursors>` returns events since the per-table cursor.
2. Push: `POST /sync` with local events not yet acknowledged. Server returns ACKs with `server_clock_ns` populated.
3. Annotations: per-document Automerge `getChanges(lastSyncState)` → server merges, returns merged changes back.

The sync runs through the WatermelonDB `synchronize()` API, but the implementation lives in `aimvision-core::sync` (Rust) and is exposed via UniFFI. The TypeScript layer just drives the cycle.

Server cursor is HMAC-signed so a malicious client can't roll its cursor backward and force a full re-pull DOS.

---

## 9. Background Upload

A 10-minute 4K clip from Hero 13 is approximately 1.5 GB. Upload happens in the background, resumable, chunked, and idempotent.

**iOS:** `URLSessionConfiguration.background(withIdentifier:)` persists across app suspension/termination and resumes via delegate on re-launch; **`BGProcessingTaskRequest`** (not `BGAppRefresh` — 30 s windows are useless for 1.5 GB clips) initiates new uploads at session end and can require power + Wi-Fi. Both are necessary: `URLSession` continues in-flight uploads; `BGProcessingTask` starts queued ones.

**Android:** `WorkManager` `OneTimeWorkRequest` per file, chained via `WorkContinuation`. Defaults: `setRequiredNetworkType(UNMETERED)` + `setRequiresCharging(true)`, **user-overridable** via in-app settings (federation rigs on hotspots need this). `setExpedited` on first chunk so the notification surfaces immediately. Foreground service with progress notification required on Android 14+ (`FOREGROUND_SERVICE_DATA_SYNC` permission with declared reason).

**Protocol — tus.io over S3 multipart:** 5 MB chunks, each independently retryable; tus daemon owns multipart state server-side. **Idempotency** via `Upload-Metadata` carrying SHA-256 + UUID v7 client upload ID; backend dedupes on SHA-256 (200 with existing remote URI on hit). **SHA-256 on-device pre-upload** computed in Rust core via `sha2` (streamed, never buffered) — also written to `recordings.sha256` for local dedupe. Resume via tus `HEAD` → `Upload-Offset`. TLS pinned (§11).

### Upload state machine

`pending → uploading → paused → uploading → complete` (happy path), with `failed` and `orphaned` terminal states. `orphaned` means the local file was deleted but the upload was incomplete — surfaced to the user with a "re-record from camera SD" option (since GoPro retains the original).

---

## 10. Battery and Thermal Budget

Targets from `10-performance-benchmarker.md` §"Battery + Thermal Targets":

- **<18 %/hour iPhone 13** during live session with preview + pose overlay, screen at 50 % brightness.
- **<22 %/hour Pixel 6a** under same conditions.
- Thermal: sustained 60-minute session at 35 °C ambient (Egypt baseline) without throttling. Phone CPU/GPU package ≤ 42 °C. **`ProcessInfo.thermalState ≤ .serious`** (iOS) and **`PowerManager.currentThermalStatus ≤ THERMAL_STATUS_SEVERE`** (Android) is the operational ceiling — anything beyond and we degrade.

**Required to hit budget:** hardware H.264 decode (VideoToolbox/MediaCodec) — software decode forbidden (~35 %+/hr); ML on ANE/NNAPI/QNN-HTP — CPU inference forbidden, GPU inference de-preferred on iOS; Wi-Fi PSM disabled during session, re-enabled between; Skia GPU rendering, never CPU canvas; GPS at 1 Hz or off; preview pauses when pocketed (`UIDevice.proximityState` / `Sensor.TYPE_PROXIMITY`).

### Graceful degradation ladder (per Performance review §Thermal)

```
42 °C (ProcessInfo == .fair)    → drop pose to 5 fps
44 °C (ProcessInfo == .serious) → drop YOLO entirely, keep audio + preview
46 °C (ProcessInfo == .critical)→ drop preview to 12 fps, keep audio + recording
48 °C                           → audio-only mode; banner: "Thermal protection active.
                                   Recording continues; live overlay paused."
```

The temperature thresholds on Android map onto `THERMAL_STATUS_*` constants. We poll every 10 s and store the trace as a Sentry breadcrumb.

**Background mode (binding):** UI rendering and pose/YOLO inference pause; audio detector continues (`AVAudioSession` background category iOS; `FOREGROUND_SERVICE_MICROPHONE` Android); recording link to GoPro continues (BLE keepalive, per `05-embedded-firmware-engineer.md` §"Wi-Fi AP mode"); on resume we replay backgrounded audio shot detections into the feed.

---

## 11. Mobile Hardening

**Secrets storage:** iOS Keychain with `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly` (never `Always`, never `UserDefaults`, never `AsyncStorage` — plaintext on disk); Android Keystore-backed `EncryptedSharedPreferences` (Jetpack Security), key bound to TEE where present. JWTs, refresh tokens, GoPro Wi-Fi creds, and BLE bond artifacts all live here.

**TLS pinning + kill-switch:** SPKI pins (not leaf certs) on API + tus + media CDN endpoints, two pins active (current + next) for rotation safety; signed `pinning_config.json` fetched at app start with hard-coded fallback as remote kill-switch (roll forward without an App Store hotfix); Certificate Transparency check (iOS ATS automatic; Android CT log verifier at OkHttp interceptor).

**Encrypted-at-rest media:** iOS `NSFileProtectionComplete` (Data Protection Class A — files inaccessible while locked, tus handles resumption between unlocks); Android `EncryptedFile` (Jetpack Security) with `AES256_GCM_HKDF_4KB`, key in Keystore.

**GoPro evil-twin defense:** pin BSSID (recorded at first pairing) **and** camera serial (queried over BLE post-Wi-Fi-join, before any auth-bearing HTTP call). Mismatch → abort with "this is not your camera; re-pair." Check runs in Rust (`transport-gopro` crate). A range full of GoPros and member phones is a perfect malicious-AP environment; one pin is not enough.

**FFI input validation:** UniFFI inputs validated at the Rust boundary (UTF-8 guaranteed; enums exhaustively matched); JNI inputs validated in the Kotlin wrapper before crossing into Rust (sizes, format enums, alignment); Swift bridging-header inputs checked at Swift level. Rust treats raw pointers as untrusted (`NonNull::new` + size checks).

**CI security tooling:** `cargo audit` + `cargo deny` (license allowlist, banned crates, duplicate-version checks) on every PR; `detekt`/`ktlint` (Android), SwiftLint/SwiftFormat (iOS), `eslint-plugin-security` (JS); MASVS Level 2 checklist quarterly.

---

## 12. PrivacyInfo.xcprivacy (iOS 17+)

Mandatory since May 2024. A missing or incomplete `PrivacyInfo.xcprivacy` bundle is an **automatic App Store rejection**. We add this in **Sprint 4** alongside the iOS native module bringup. Required API reasons:

| API category                                 | Reason code                                          | Why we need it                                                                     |
| -------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `NSPrivacyAccessedAPICategoryUserDefaults`   | `CA92.1` (current user only)                         | Settings, sync cursors, ephemeral cache.                                           |
| `NSPrivacyAccessedAPICategoryFileTimestamp`  | `C617.1` (display to user / files only owned by app) | Sync ordering; recording timestamps in the local feed.                             |
| `NSPrivacyAccessedAPICategorySystemBootTime` | `35F9.1` (measure event time precisely)              | Monotonic clock anchor for shot event sequencing (`mach_absolute_time` reference). |
| `NSPrivacyAccessedAPICategoryDiskSpace`      | `E174.1` (display to user)                           | Pre-recording disk space check — refuse session if <5 GB free.                     |
| `NSPrivacyAccessedAPICategoryActiveKeyboard` | n/a                                                  | We do not introspect keyboards; declare empty.                                     |

In addition, `NSPrivacyTrackingDomains` is empty (we don't track across apps) and `NSPrivacyTracking` is `false`. `NSPrivacyCollectedDataTypes` declares: video recording, performance data (Sentry), crash data (Sentry), and email (account). All linked to user identity (we have accounts), not used for tracking.

**Side-effect declarations for our SDKs (third-party):** Sentry, Statsig, Expo Updates, AVFoundation (camera APIs), CoreBluetooth, CoreLocation (range location, optional). Each of these ships its own `PrivacyInfo.xcprivacy`; the App Store assembles them into the app-level manifest. We pin SDK versions known to ship valid manifests.

---

## 13. OTA Updates, Feature Flags, Crash Reporting

All three from **Sprint 3**, not Sprint 22 (per `04-mobile-app-builder.md` §"Things missing"). Egypt validation without crash telemetry is flying blind.

**OTA — Expo EAS Update:** `expo-updates` wired to EAS. Channels `production`/`staging`/`dev`; federation appliances pin to `production` with manual update gates. Background download, apply on cold start, fallback to bundled JS on verify fail. Not CodePush (Microsoft sunsetting 2025). Rust core changes are **not** OTA-able — they go through TestFlight + Play Beta promote-to-production.

**Feature flags — Statsig:** flags + dynamic config + A/B experiments; consumed at session boot, cached in MMKV with TTL, offline defaults shipped in bundle (federation appliance with no internet still behaves). Rollout rules by tier (`solo`/`club`/`federation`), region (`EG`/`US`/...), device tier (`high`/`mid`/`low`). Used for ML rollouts (5 % shadow → 50 % canary → 100 %), coach-mode tone, paywall layouts.

**Crash + performance — Sentry:** `@sentry/react-native` covers RN JS + Hermes stack traces; `sentry-cocoa` and `sentry-android` auto-enabled; **`sentry-rust` panic hook** in core init reports Rust panics to the same project. `sentry-cli` in CI for Hermes source maps + dSYM/ProGuard mapping upload. Performance spans on the live session screen specifically. OpenTelemetry from Sprint 6 (per `10-performance-benchmarker.md` §Instrumentation) is the complementary trace view.

---

## 14. Accessibility Floor (Sprint 3, Not Sprint 18)

Older shooters have presbyopia, tremor, gloves. Retrofitting in Sprint 18 means redoing every component.

**Minimum requirements (binding):**

- **Dynamic Type:** 17 pt body floor, scales to `accessibilityExtraExtraExtraLarge` (iOS) / `fontScale = 2.0` (Android). No hard-coded `fontSize`; all text via `useDynamicTypeSize`.
- **Tap targets:** 44 × 44 pt minimum (HIG); **primary actions 56 × 56 pt** (UX review older-shooter default — gloves + tremor). Primary = record start/stop, shot tag, voice note.
- **VoiceOver/TalkBack labels** on every interactive element. Per-shot rows synthesize "Shot 12, station 4, diagnosis: head lift, tap for details" — no raw "Button" labels.
- **Reduced motion:** disable pose-skeleton motion trail + parallax when `UIAccessibility.isReduceMotionEnabled` / `Settings.Global.TRANSITION_ANIMATION_SCALE == 0`; transitions cross-fade.
- **"Range Mode"** opt-in profile bumps font, contrast, tap targets together for outdoor glare + gloves; toggle in Settings, persisted in MMKV, surveyed at first session.
- **Hearing-aid-friendly haptics:** every audio cue paired with Core Haptics (iOS) / `VibrationEffect` predefined (Android).

**Audit gates:** `AccessibilityInspector` on iOS PRs touching screens; `axe-android` in instrumentation tests; manual VoiceOver/TalkBack on every RC; WCAG AA (4.5:1) body, AAA (7:1) primary, verified in CI.

---

## 15. i18n / RTL (Sprint 3)

Egypt is the launch market; Arabic is RTL. Retrofitting in Sprint 18 is a 2-sprint slip risk.

- **`i18next` + `react-i18next`.** JSON catalog per locale, extracted via `i18next-parser`, human-translated with shooting-sports glossary review.
- **EN-US** baseline (Sprint 3); **AR-EG** (Sprint 8, ahead of Sprint 19 Egypt validation); **ES deferred** (Sprint 24+, not V1 launch).
- **RTL-safe primitives from Sprint 3:** logical properties only (`paddingStart`/`marginEnd` — RN 0.76 + Yoga 2.x); no `transform: translateX` for layout; directional icons flip via an `RTLAware` wrapper reading `I18nManager.isRTL`; Eastern Arabic numerals (٠-٩) default for AR-EG (toggle); `Intl.DateTimeFormat` always, never hand-formatted dates.
- **Test:** Storybook renders every screen with `forceRTL=true`; visual snapshot diff in CI. Pseudo-localization (`[!! Lörém !!]`) builds for QA to catch hard-coded strings.

---

## 16. Device Farm Coverage

Per `04-mobile-app-builder.md` §"Things missing" #5. The team's iPhone 16 Pros are not the median shooter device. We test on real-world budget hardware.

### Required device matrix (binding)

**iOS:**

- iPhone 12 (A14, iOS 17 floor)
- iPhone 13 (A15, the median shooter device — primary baseline)
- iPhone 15 (A16, current-gen)

**Android:**

- Pixel 6a (Tensor G1, Android 13 → 14 — the budget Android floor)
- Pixel 8 (Tensor G3, Android 14 → 15 — current Pixel reference)
- Galaxy A54 (Exynos 1380, mid-tier Samsung — the Egypt mid-market)
- Galaxy S22 (Snapdragon 8 Gen 1, QNN-HTP reference — flagship Snapdragon)

**Tooling:** Firebase Test Lab (Android, free tier covers Pixel + Galaxy matrix; Robo + instrumentation); AWS Device Farm _or_ BrowserStack App Live (iOS) — start BrowserStack for manual QA, add AWS Device Farm once XCUITest suites land; Maestro (mobile.dev) for cross-platform E2E nightly.

**CI gates:** per-PR smoke flow (login → start session → record 30 s → stop) on iPhone 13 + Pixel 6a (~8 min); nightly full matrix regression (~90 min); pre-release thermal/battery soak (60-min synthetic session via the Sprint 8 phone-on-tripod rig from `10-performance-benchmarker.md` §Instrumentation #4).

---

## 17. Sprint Resequencing Summary

Per `04-mobile-app-builder.md` §"Sprint resequencing", the V1 plan's mobile sequencing has five binding corrections:

1. **Sentry/Crashlytics, feature flags (Statsig), OTA (Expo EAS Update), `PrivacyInfo.xcprivacy`, and battery/thermal instrumentation move from Sprints 19/22 → Sprint 3-4.** Non-negotiable infrastructure; without these, Egypt validation is flying blind and any iOS submission gets auto-rejected.

2. **Older-device lite-model variants (RTMPose-Tiny, YOLOv8n @ 320, etc.) move from Sprint 20 [P1] → Sprint 9 [P0].** Quantization is a model-architecture decision (Core ML Tools `cto.coreml.optimize`, NNAPI `ANEURALNETWORKS_TENSOR_QUANT8_ASYMM`), not a polish step. Train the lite variant in parallel with the full one starting Sprint 9.

3. **App Store firearms positioning moves from Sprint 22 → Sprint 1.** File a TestFlight build with neutral metadata ("Olympic shooting sports analytics", "ISSF training", screenshots showing pose skeletons + charts, no shotguns visible) by Sprint 6 to surface rejection signals 12 sprints early. ShotKam ships as "trap/skeet camera"; MantisX ships as "shooting performance"; copy that exact tone. Preserve the PWA fallback (Sprint 1 web shell) as a real deployment target.

4. **Offline-first DB (WatermelonDB) + sync engine (LWW + Automerge 2.0) move from Sprint 12 → Sprint 5.** This is a foundational data-model decision; bolting it on after the schema solidifies forces a rewrite of every reducer, hook, and screen that touches data.

5. **Accessibility + i18n scaffolding (string extraction, RTL-safe layout primitives, Dynamic Type, 56 pt primary tap targets) move from Sprint 18 → Sprint 3.** Arabic RTL retrofitted in Sprint 18 is a 2-sprint slip risk; accessibility retrofitted in Sprint 18 means redoing every component.

---

**End of specification.** Deviations require an ADR. Reviewers' verdicts ratified above are non-negotiable for V1.
