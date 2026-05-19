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
3. **Slice 3:** Real-time frame processor — Vision Camera worklet pulls YUV frames on the worklet thread, hands them to a native Obj-C++/JNI shim, which crosses into `aimvision-camera-core` via the existing `extern "C"` media plane. A new backend crate `aimvision-camera-phone` becomes the _third_ `CameraMedia` implementation alongside the mock and the (still pending) GoPro backend.
4. **Slice 4:** Dual-phone capture + audio cross-correlation for multi-camera alignment. No `!MSYNC` from phones, so alignment falls back entirely on the audio cross-correlation path already specified in [docs/multi-camera-sync-spec.md](../multi-camera-sync-spec.md).

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
