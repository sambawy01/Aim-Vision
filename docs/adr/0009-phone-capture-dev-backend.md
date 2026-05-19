# ADR-0009: Phone Capture as a Dev-Mode Camera Backend

**Status:** Accepted · **Date:** 2026-05-19 · **Owner:** Mobile App Builder (with Software Architect concurrence)

## Context

The V2 plan and [ADR-0003](0003-rust-camera-core-split.md) commit to GoPro Hero 13 as the production capture device, with the federation tier eventually moving to a USB-C tethered multi-camera rig and (Phase 2+) AIMVISION custom hardware. The trait split in ADR-0003 anticipates multiple `CameraControl` + `CameraMedia` backends behind a stable trait surface, with a mock backend already shipped under `aimvision-camera-core/crates/aimvision-camera-mock` for fault-injection tests.

Hero 13 hardware is not yet in the team's hands. Per the V2 sprint plan and the current CLAUDE.md handoff, the items gated on hardware include S4 EPIC 4.1 (the real GoPro path) and S5 EPIC 5.5 (the first Egypt range capture). The classical audio shot detector (PR #35) and pose evaluation harness (PR #37) currently exercise on synthetic inputs only; the diagnostic head sits idle in `aimvision-ml/` until it has real shooter footage and audio to train on.

The team needs **real range capture in days, not weeks**, to:

1. Validate the audio shot detector against actual muzzle-blast + clay-impact + ambient mixtures.
2. Validate the pose pipeline against real shotgun stances under range lighting (vs. synthetic shooter-stance generator).
3. Surface integration issues in the post-session backend pipeline (`Recording` upload state, Temporal workflow per [ADR-0007](0007-temporal-orchestration.md)) before Hero 13 paperwork clears.
4. Demo the loop end-to-end to the Egypt federation design partner without telling them "the camera comes later."

The deliberate choice is to **add a phone-camera backend behind the existing camera-core trait surface, scoped to dev/internal use, with a hard line that Hero 13 remains the product spec**.

## Decision

**We add a phone capture path as a _development-mode_ backend behind the same `Camera*` trait surface defined in ADR-0003. Hero 13 stays the production camera. Phone capture is never marketed, sold, or shown to a coach customer; it exists so the team can produce real range data while procurement closes.**

This is implemented in four slices, each landed as its own PR:

1. **Slice 1 (this ADR's landing slice):** RN client `aimvision-mobile/` gets a `react-native-vision-camera` v4 integration: permissions, a `/app/capture/phone` screen with start/stop record-to-local-MP4 using Vision Camera's built-in `recordVideo`. No frame processor yet, no upload yet. A pure-TS recording state machine handles the lifecycle and is unit-testable without a device.
2. **Slice 2:** Backend ingest — `POST /v1/sessions/{id}/recording` accepting a multipart MP4 upload, mapped onto the existing `Recording.upload_state` lifecycle. Triggers the same post-session Temporal workflow as a Hero 13 recording would.
3. **Slice 3:** Real-time frame processor — three independently-shippable sub-slices because the surface area touches RN, native Swift/Kotlin, AND Rust. Each sub-slice is verifiable on its own:
   - **Slice 3a (landed):** Vision Camera + `react-native-worklets-core` frame processor wired up in `CapturePhoneScreen`. The worklet runs per-frame on the camera thread, writes frame metadata (count, timestamp, width/height, pixel format) through worklets-core shared values, and the screen renders a live "fps · count · resolution · format" banner via a 500 ms poll. Independent of native code: this proves the worklet pipeline reaches React. Pair: the new `aimvision-camera-phone` Rust crate ships in this same slice with a safe-Rust `push_frame` / `push_audio_chunk` API and a `CameraMedia` impl backed by bounded ring buffers (drop-oldest on overflow, dropped-counters for backpressure observability). 8 Rust unit tests + 9 TS helper tests.
   - **Slice 3b (landed):** Native frame-processor plugin — Swift + Obj-C registration glue on iOS, Kotlin plugin + `ReactPackage` on Android. Sources live in `aimvision-mobile/plugins/phone-frame-sink/{ios,android}/`. An Expo config plugin (`withPhoneFrameSink.ts`) wires them in at `expo prebuild` time: `withDangerousMod` copies the sources into the generated project trees, `withXcodeProject` adds the iOS files to a new `PhoneFrameSink` group in the .pbxproj, and `withMainApplication` registers the Android package with idempotent text rewrites. Slice 3b's plugin returns frame metadata (source tag, width, height, timestampNs, pixelFormat, orientation) — exactly enough to prove the native path runs. The screen calls `VisionCameraProxy.initFrameProcessorPlugin('avPhoneFrameSink', {})` and the worklet invokes the native plugin per-frame, falling back to slice-3a's JS metadata path when the plugin isn't registered (e.g. before `expo prebuild`). 10 unit tests cover the Expo config plugin's prebuild-time logic in isolation; the native compile + on-device runtime stays a manual verification step.
   - **Slice 3c (landed):** C ABI bridge — the native plugin from 3b now calls into `aimvision-camera-phone` via the `extern "C"` media plane from ADR-0003. The Rust crate exposes the C ABI in `crates/aimvision-camera-phone/src/ffi.rs` with a matching C header at `include/aimvision_camera_phone.h`; `unsafe_code` is `deny`-at-crate-root with `#[allow]` scoped to the `ffi` module and per-call SAFETY comments. Six FFI surface functions: `aimvision_phone_camera_new` / `_free` / `_push_frame` / `_push_audio_chunk` / `_dropped_frames` / `_dropped_audio`. The crate now builds `staticlib` + `cdylib` + `rlib` so iOS can link the static library directly and Android can load the shared object. On the mobile side, `AVPhoneFrameSinkBridge.swift` resolves the C ABI via `dlsym` against the main bundle (fails soft if the static library isn't linked yet → plugin reports `native-ios` instead of `native-ios-rust`); `AVPhoneFrameSinkBridge.kt` declares the JNI external functions and tries `System.loadLibrary("aimvision_camera_phone_jni")` against the new `aimvision-camera-phone-jni` workspace crate (an in-Rust JNI shim that wraps the C ABI — see slice 3c-jni below). The Expo config plugin ships the new bridge sources alongside the slice-3b plugin code. The end-to-end zero-copy pixel-data path (real `IOSurface` / `AHardwareBuffer` handles) is the next sub-slice (3c-followup); slice 3c lands the bridge contract so the wire format is fixed. **9 new Rust FFI unit tests** (17 total in the crate) cover NULL handling, capacity rejection, eviction-counter integration, and ABI-discriminant stability. The phone backend is now the _third_ `CameraMedia` implementation alongside the mock and the (still pending) GoPro backend.
   - **Slice 3c-jni (landed):** Android JNI shim — a new workspace crate `aimvision-camera-phone-jni` (`cdylib`, depends on `aimvision-camera-phone`, uses the `jni` 0.21 crate) exports four `Java_com_aimvision_app_phoneframesink_AVPhoneFrameSinkBridge_native*` symbols and forwards each into the C ABI. `cargo build -p aimvision-camera-phone-jni --release --target aarch64-linux-android` (or armv7/x86_64) produces `libaimvision_camera_phone_jni.so` for `android/app/src/main/jniLibs/<abi>/`. 3 host-side unit tests cover the `jlong ↔ *mut AimvisionPhoneCamera` round-trip, the `jint → AimvisionFrameFormat` mapping, and NULL handling. The on-device verification (actual `System.loadLibrary` + `nativePushFrame` invocation) stays a manual step.
4. **Slice 4 (landed — algorithm):** Audio cross-correlation alignment in `aimvision_ml.inference.audio_xcorr`. Implements the fine-alignment layer from [docs/multi-camera-sync-spec.md](../multi-camera-sync-spec.md) §3.2: 200 Hz–8 kHz Butterworth bandpass (zero-phase via `filtfilt`), windowed cross-correlation per shot, three-point parabolic peak interpolation for sub-sample resolution, normalized-correlation [0, 1] confidence metric (default threshold 0.3 separates real blasts from noise floor at 1/√N), and a multi-shot driver that medians per-shot offsets so an echo or missed shot can't drag the session alignment. 12 synthetic-signal tests cover bandpass behaviour, integer + fractional-sample offset recovery, noise tolerance, search-window guard, median-vs-outlier robustness. **Phone-only slice 4 still needs a dual-phone capture coordinator on the mobile side** (session-start handshake to share a coarse clock + per-phone shot detection feeding the same xcorr driver) — that lands when the second phone-pair test hardware is on the bench. The algorithm crate is what blocked: it can now be wired up the moment dual-phone capture lands.

### Constraints we accept

| Capability                                | Hero 13 (product)                          | Phone (dev-mode)                                                                                                                   |
| ----------------------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Multi-camera sync via `!MSYNC`            | Yes (sub-frame)                            | **No** — phones have no equivalent. Audio cross-correlation only, sub-frame accuracy unreliable.                                   |
| GoPro Labs streaming overlay              | Yes                                        | **No**                                                                                                                             |
| HILIGHT / external trigger                | Yes (BLE)                                  | **No** in slice 1; possibly a software hilight tap in slice 3                                                                      |
| Mount stability (chest, helmet, gunsight) | Designed for it                            | Phone tripod/clamp only; FOV limited                                                                                               |
| Audio quality                             | Hero 13 mic array, decent low-end roll-off | Varies dramatically by phone; shot-detection thresholds must be re-calibrated per device                                           |
| Pose-estimation viability                 | Consistent FOV/resolution                  | Varies dramatically by phone; floor we set: 1080p30, Pixel 7 / iPhone 14 or newer                                                  |
| ML model gate metrics                     | Recorded against Hero 13 footage           | Phone capture is **not** an admissible training source for production model gates without explicit per-device calibration sign-off |

### Constraints we enforce in code

- The phone backend is keyed by a feature flag (`capture.phone_backend_enabled`, default off in production builds) so the dev-mode entry point cannot be hit by a customer.
- `Recording.source_kind` (added in slice 2) records which backend produced the file. Backend-side reports filter `source_kind = "phone-dev"` out of any aggregate that would be shown to a customer.
- The Hero 13 backend in `aimvision-camera-core` stays the canonical reference. When the two backends disagree on a contract (e.g., frame format, clock discipline), Hero 13 wins; the phone backend adapts.
- This ADR is the standing reminder. Re-evaluate at the end of Phase 2 (same gate as ADR-0003): if Hero 13 has shipped and stabilized, the phone backend is moved to `aimvision-camera-core/crates/aimvision-camera-phone-dev/` and tagged as no longer part of the supported matrix.

## Alternatives considered

### Alternative A: phone-recorded MP4 → backend ingest only, no frame processor

Recorded entirely with `react-native-vision-camera`'s built-in `recordVideo`, uploaded as a complete file, processed only post-session. Simpler, ships in ~2 days, exercises the post-session Temporal pipeline immediately.

**Rejected as the _end-state_, accepted as the _first slice_.** Real-time frame processing is what the production Hero 13 path requires, and building it later means a parallel data path that diverges. Slices 1 and 2 in the decision above are exactly this alternative; we go further in slices 3–4 so the dev-mode capture exercises the production code path, not a sidetrack.

### Alternative B: phone capture as the V1 product (drop Hero 13)

Skip Hero 13 entirely, ship to coaches with their iPhones/Androids.

**Rejected.** Three of the five differentiators in the V2 plan depend on hardware Hero 13 provides and a phone cannot: external HILIGHT trigger, sub-frame multi-camera sync via `!MSYNC`, consistent FOV/audio across the entire customer base. A phone-only product is a different (worse) product, and abandoning Hero 13 strands the federation tier's USB-C tether plan and the future custom-hardware roadmap.

### Alternative C: wait for Hero 13

Don't capture any real data until product hardware arrives.

**Rejected.** Hardware procurement is a multi-week external dependency, the ML eval harnesses already exist and would sit idle, and the Egypt design partner expects something to look at this quarter. Synthetic data is sufficient for unit-level gates (and we have it) but it is not sufficient for the audio-shot-detector calibration work or the diagnostic-head sanity check.

## Consequences

### Positive

- Unblocks the audio shot detector and pose harness with real range data within a slice of Hero 13 procurement.
- Exercises the full backend ingest + Temporal pipeline path early, surfacing integration bugs before product launch.
- Keeps the camera-core trait surface honest — by the time Hero 13 arrives the trait has three working backends (mock, phone, GoPro) and any leaky abstraction will already have been caught.
- Gives the federation design partner a demonstrable end-to-end loop without waiting on customs.

### Negative

- The `aimvision-mobile/` codebase grows native-camera complexity (Vision Camera, frame processors, native shims) earlier than the original V2 sprint plan scheduled it. Mitigated by the slice breakdown: slice 1 is plain TS + Expo plugin only, no native shims yet.
- Maintenance burden: phones are a fragmentation hellscape. We mitigate by setting an explicit minimum device floor (Pixel 7 / iPhone 14 or newer) and scoping the entire phone backend as dev-only.
- Risk of "phone is good enough" rot — multi-camera sync via `!MSYNC` is genuinely a differentiator and audio-correlation-only multi-camera is a step down. This ADR is the standing reminder, and the Phase 2 re-evaluation gate is the structural enforcement.

### Neutral

- `docs/camera-integration-spec.md` adds a "Dev-mode phone capture" section documenting the phone backend's capability matrix vs. Hero 13. New contributors read the same canonical doc and understand the dev/product split.

## Links

- [ADR-0003: Rust Camera-Core with Split Traits](0003-rust-camera-core-split.md) — the trait surface this backend slots behind.
- [ADR-0007: Temporal Orchestration](0007-temporal-orchestration.md) — the post-session pipeline that slice 2's upload feeds.
- [docs/camera-integration-spec.md](../camera-integration-spec.md) — to be updated alongside slice 1.
- [docs/multi-camera-sync-spec.md](../multi-camera-sync-spec.md) — the audio cross-correlation path slice 4 depends on.
