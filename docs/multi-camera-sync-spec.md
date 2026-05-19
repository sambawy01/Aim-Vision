# AIMVISION Multi-Camera Sync Specification

**Status:** Draft v1.0
**Owner:** Embedded Firmware Engineer
**Date:** 2026-05-06
**Related:** `docs/camera-integration-spec.md`, `docs/reviews/05-embedded-firmware-engineer.md` §"Multi-Camera Sync Recommendation", `docs/reviews/10-performance-benchmarker.md`, Sprint Prioritizer review (V1.5 deferral)

This document specifies how AIMVISION federation-tier rigs synchronize 2–3 GoPro Hero 13 cameras to within sub-millisecond per-shot accuracy without genlock hardware. It is the technical foundation for triangulated 3D pose at federation tier, but full multi-cam validation is **deferred to V1.5** per the Sprint Prioritizer review — V1 ships single-camera Solo + Club, and 2-camera architecture-only for federation.

---

## 1. Problem Statement

Federation tier requires 2–3 cameras to triangulate 3D body and gun pose. The geometry is unforgiving:

- At 60 fps, a single-frame timing error is **~16.67 ms**.
- A shotgun athlete's gun swings at **~20°/frame** during the lead phase of a fast crossing target.
- A 16 ms cross-camera misalignment translates to a **0.5° geometric error in the gun-pose estimate**, which at 5 m subject-to-camera distance is a **~4 cm 3D position error** at the muzzle.
- For diagnostic claims like "muzzle leads target by 1.2 m at break point," 4 cm error is the floor of credibility, not the ceiling.

We need **sub-millisecond per-shot alignment** between cameras for a tier that publicly advertises triangulated 3D analytics. Anything looser is hand-wave.

---

## 2. Hardware Genlock Is Unavailable

GoPro Hero 13 exposes:

- No genlock pin.
- No frame-trigger input.
- No external sync clock input.
- No PTP slave mode.

The Open GoPro Labs `!MSYNC` feature is **timestamp-based, not true genlock** — the cameras do not phase-lock their sensors to a common clock; they only stamp frames against a shared reference clock that is itself broadcast over BLE with finite resolution. Frames remain captured at independent sensor exposure phases.

We accept this and design around it. A hardware-genlock-quality solution would require the V3 custom AIMVISION hardware roadmap (`docs/camera-integration-spec.md` §16.1).

---

## 3. Hybrid Sync Recommendation

The architecture is a two-layer hybrid: coarse alignment from `!MSYNC`, fine alignment from audio cross-correlation, with continuous drift compensation.

### 3.1 Coarse: Open GoPro Labs `!MSYNC`

- Mechanism: master camera (or a phone running the operator app) broadcasts a clock reference over BLE; slave cameras tag every frame's GPMF timecode against that reference.
- Measured alignment: **~5–15 ms between two Hero 13s at 1 m distance, 2.4 GHz clean RF.**
- Available only on Labs firmware (see `docs/camera-integration-spec.md` §10).
- Our use: the BLE-broadcast clock is the _anchor frame_. We log every camera's MSYNC offset at session start and every 60 s thereafter.

### 3.2 Fine: audio cross-correlation on muzzle blast

A 12-gauge muzzle event is a sharp, broadband impulse — rise time ~0.3 ms, peak-to-trough ~3 ms. This is a near-ideal cross-correlation target.

- Pipeline: per-camera audio stream → 48 kHz mono PCM → bandpass 200 Hz–8 kHz → cross-correlate windowed segments around each detected shot.
- Output: per-camera, per-shot offset in samples (resolution: 1/48 kHz = **20.83 µs**, refined further by parabolic sub-sample interpolation around the discrete xcorr peak — typical recoverable resolution **< 1 µs** under noise-free conditions, **< 20 µs** at 30 dB SNR).
- "Free" cost — the shot detector already runs on the audio path for shot detection; the xcorr computation is incremental.
- Required: the muzzle blast must reach all cameras. At a 5 m baseline between cameras, propagation delay is 5/343 ≈ 14.6 ms — this is the _signal_ we measure, not error. We back out the geometry from the calibrated camera positions (§4).

**Implementation:** `aimvision_ml.inference.audio_xcorr` (Python, in `aimvision-ml/`). Public surface: `cross_correlate_shot(a, b, sample_rate_hz)` for one shot pair, `align_camera_pair(a_pcm, b_pcm, shot_times_in_a_s, sample_rate_hz)` for the multi-shot driver that medians per-shot offsets. Confidence is the normalized cross-correlation coefficient in [0, 1]; the pair-level driver returns the median over confident shots only, so a single bad shot (echo, missed shot) can't drag the session offset. 12 unit tests cover bandpass behaviour, integer + fractional-sample offset recovery via parabolic interpolation, noise tolerance, search-window guard, and median-vs-outlier robustness. Hardware-verified calibration arrives in Sprint 5 EPIC 5.5 (first Egypt range capture).

### 3.3 Drift compensation

- Two Hero 13s on Labs `!MSYNC`: **expect 10–30 ms accumulated clock drift over 1 hour.** This is documented in firmware review §"Multi-Camera Sync".
- Drift is roughly linear (oscillator temperature-coefficient dominates).
- We **re-anchor with audio every shot.** A typical federation session has 80+ shots in 30 min, so anchoring is dense. Between shots, we linearly interpolate the offset.
- If a stretch of >5 minutes elapses without a shot, we issue a synthetic anchor by hilight-pulse-then-record: a soft hilight tag emitted on each camera; the BLE round-trip latency is measured and used as a coarse anchor.

### 3.4 Why not pure audio xcorr without MSYNC?

Audio alone doesn't bootstrap. The first shot's offset is unknown until we know the cameras' relative clocks within ±50 ms (the search window for xcorr). MSYNC provides that bootstrap. Without MSYNC we'd need a manual clap-board, which is operationally fragile.

### 3.5 Why not pure MSYNC without audio xcorr?

MSYNC alone gets us to ~10 ms p50, ~25 ms p95. That's worse than one frame at 60 fps and not federation-tier credible. The audio refinement closes the gap by three orders of magnitude.

---

## 4. Calibration

Geometric calibration of the multi-camera rig — the intrinsic and extrinsic parameters — is required before triangulation has meaning. Sync is the time axis; calibration is the space axis.

### 4.1 Pattern: ChArUco board, NOT plain checkerboard

- **ChArUco 12×9** with 30 mm squares and 22 mm AR markers (DICT_4X4_50).
- Why ChArUco over checkerboard: **ChArUco survives partial occlusion.** When athletes walk through frame during a federation session, a checkerboard detection fails entirely; ChArUco recovers per-marker even with 40% occlusion.
- The board ships as a printed-on-aluminium 60×40 cm plate in the federation kit.

### 4.2 Algorithm

```
1. Per-camera intrinsics:
     OpenCV calibrateCameraCharucoExtended()
     → K (intrinsic matrix), distortion_coeffs (5-param Brown-Conrady)
2. Multi-camera extrinsics:
     OpenCV solvePnP per camera against shared ChArUco frames
     → R (rotation), t (translation) per camera relative to camera 0
3. Refinement:
     Ceres bundle adjustment (cost function: reprojection error)
     → refined K, distortion, R, t simultaneously
```

Why Ceres bundle adjustment? OpenCV's `stereoCalibrate` is greedy and noise-sensitive; bundle adjustment jointly optimises intrinsics + extrinsics + 3D point cloud and converges to materially better extrinsics in practice (~30% reprojection-error reduction vs OpenCV-only).

**Implementation scaffold:** `aimvision_ml.inference.camera_calibration` (Python, in `aimvision-ml/`) ships the math layer of step 3 above as a pure numpy + scipy bundle-adjustment solver. Public surface: `ChArUcoBoard` (3D corner geometry for the 12×9 spec board), `CameraIntrinsics` + `CameraExtrinsics` (matching the persistence schema in §4.5), `project_points` (pinhole + Brown-Conrady 5-parameter distortion, OpenCV-compatible coefficient layout), and `refine_calibration` (joint refinement via `scipy.optimize.least_squares` with Rodrigues 3-vector rotation parameterization). 12 synthetic-board tests cover projection sanity, distortion behavior, noise-free intrinsic recovery, noise-tolerant focal recovery (within 3% at 0.3 px corner noise), radial-distortion recovery, and input validation. **What's still pending: the ChArUco _detection_ step itself** — `cv2.aruco.detectMarkers` + `cv2.aruco.interpolateCornersCharuco` + `cv2.calibrateCameraCharucoExtended` for the initial seed. That step needs `opencv-python` which we'll add as an `aimvision-ml[vision]` extra in a follow-up sub-slice once the federation rig is bench-ready.

### 4.3 Expected error

- **Reprojection error: 2–3 mm @ 5 m baseline** with the 12×9 ChArUco and 1080p capture.
- Sufficient for swing-path geometry (the muzzle moves ~0.5 m during a typical break — 2 mm precision is 0.4% of signal).
- **Insufficient for sub-cm head-stability claims.** We do not market head-stability metrics at federation tier on V1 hardware. V3 custom hardware with hardware genlock + higher resolution is needed for that.

### 4.4 Cadence

- **Re-calibrate per session.** Cameras get bumped, tripods shift, thermal expansion of the alu plate changes the rig by ~0.5 mm over a 30 °C temperature range.
- **Mid-session recalibration trigger:** if reprojection error on detected ChArUco frames in incidental footage spikes >2× baseline, prompt operator to re-run calibration before next string.
- The calibration sequence is operator-led, takes ~90 s, and is gated before recording starts.

### 4.5 Persistence

Per camera per session, the local event store records:

```rust
struct CameraCalibration {
    session_id: SessionId,
    camera_id: CameraId,
    intrinsics_K: [[f64; 3]; 3],       // 3x3 matrix
    distortion_coeffs: [f64; 5],       // k1, k2, p1, p2, k3
    extrinsics_R: [[f64; 3]; 3],       // rotation relative to camera 0
    extrinsics_t: [f64; 3],            // translation relative to camera 0
    reprojection_error_px_p95: f32,
    calibration_ts_ns: u64,
    charuco_frames_used: u32,
}
```

This record lives on the cloud per-session; it is not implicitly carried across sessions.

---

## 5. Schema for Sync Metadata (Recording Entity)

The `Recording` entity gains explicit per-shot, per-camera sync fields. This is **baked into the schema in V1**, not Sprint 17, per firmware review — the cost of refactoring it later is much higher than carrying unused fields now.

### 5.1 Fields

```rust
pub struct ShotEvent {
    // Identity
    pub session_id: SessionId,
    pub monotonic_seq: u64,
    pub shot_id: ShotId,

    // Per-camera-per-shot sync data
    pub per_camera: Vec<PerCameraShotSync>,

    // Cross-camera derived
    pub canonical_ts_ns: u64,          // resolved unified timestamp
    pub canonical_confidence: f32,     // 0.0..=1.0
}

pub struct PerCameraShotSync {
    pub camera_id: CameraId,
    pub camera_clock_offset_ms: f64,   // signed; relative to canonical
    pub frame_pts_ns: u64,             // raw PTS from MPEG-TS / GPMF
    pub shutter_open_ts_ns: u64,       // PTS adjusted for known sensor exposure offset
    pub is_drift_compensated: bool,    // true if linear interp from neighbouring anchors
    pub sync_method: SyncMethod,
    pub audio_xcorr_correlation_peak: Option<f32>,  // 0..=1 confidence
}

pub enum SyncMethod {
    MSync,            // !MSYNC anchored, no audio xcorr (silent shot or tape blast)
    AudioXcorr,       // audio cross-correlation refined; preferred
    ManualClap,       // operator-issued clap-board fallback
    Interpolated,     // drift-interpolated between anchored shots
}
```

### 5.2 Why every field

- `camera_clock_offset_ms` per camera per shot — the reviewer flag in firmware review §"Multi-Camera Sync"; refusing to add this in V1 = mandatory refactor in Sprint 17.
- `frame_pts_ns` — needed to map back to actual frames in post-session analysis.
- `shutter_open_ts_ns` — Hero 13 sensor exposure has a ~3 ms offset from PTS-stamping; correcting for it improves cross-camera alignment.
- `is_drift_compensated` — flagged in reports; a drift-interpolated shot is shown with a confidence asterisk.
- `sync_method` — auditability; future ML training datasets need to know data provenance.

---

## 6. 3D Pose Pipeline

The downstream consumer of synchronised multi-camera frames.

### 6.1 Architecture

```
Per-camera frame buffer (synchronised, sub-ms aligned)
  → Per-camera 2D pose: RTMPose-Wholebody (or RTMPose-l for body-only at 60 fps)
  → Triangulation via DLT (Direct Linear Transform) using calibrated K, R, t
  → Optional: VoxelPose or Multi-view Pose Transformer (MvP) for joint multi-cam refinement
  → 3D keypoint timeseries
  → Optical flow (RAFT-Tiny) for inter-frame interpolation when sync drift exceeds tolerance
```

### 6.2 Method choice

- **RTMPose-Wholebody** for per-camera 2D — production-mature, ~20 ms inference per frame on phone NPU per perf review.
- **VoxelPose / MvP** as the multi-view fusion layer — VoxelPose is the more deployed choice; MvP is newer and slightly higher accuracy on CMU Panoptic but heavier. **V1.5: VoxelPose. V2: evaluate MvP.**
- **Optical flow fallback (RAFT-Tiny)** — when sync drift exceeds tolerance (>2 ms — i.e., audio xcorr failed AND MSYNC drift accumulated), interpolate the pose between sync-confident frames using optical flow. Reduces the apparent jitter without lying about geometric accuracy.

### 6.3 What we do NOT do

- We do not run 3D pose **on-device** in V1.5 federation tier. The phone handles 2D per-camera; multi-view 3D fusion happens in the post-session backend pipeline (the 90 s post-session report budget per perf review).
- Live triangulated 3D is a V2 ambition gated on the New Architecture RN bridge (architect review §"Frame pipeline as native-only with JSI keypoint bridge") + sustained-NPU thermal validation.

---

## 7. Failure Modes

Sync is a system; systems fail.

### 7.1 One camera drops mid-session

- Detection: BLE keepalive miss × 3 = `Errored(LinkLost)`.
- Behaviour: continue with the reduced rig (1 of 2, or 2 of 3). 3D triangulation degrades to 2D-only on the remaining cameras.
- Report flag: prominent **"degraded — single camera from 14:32:17 onward"** banner on the report PDF and feed.
- Recovery: when the camera reconnects (often a thermal-cooldown cycle later), re-anchor MSYNC and resume multi-cam from that point.

### 7.2 Calibration drift

- Detection: per-frame reprojection error on incidental ChArUco-board appearance OR on stable static features (range structure) spikes >2× baseline p95.
- Behaviour: emit a `CameraEvent::CalibrationDriftSuspected` event; UI prompts operator to re-calibrate before next string.
- The current string is **not** invalidated; it is annotated as "calibration-degraded" in the report.

### 7.3 Audio anchor missing (silent shot, tape blast, etc.)

- Detection: shot detected on camera A but no corresponding transient on camera B within ±100 ms.
- Causes: physical tape blast (operator forgot to pull tape off mic), gunshot in the deep null of the mic's polar pattern, mic failure.
- Behaviour: fall back to **MSYNC-only** sync for that shot; flag `sync_method: MSync` in `PerCameraShotSync`. Confidence flag in the report — "geometric accuracy reduced for shots 12, 19, 27."
- This is graceful degradation, not session failure.

### 7.4 BLE master clock dropout (MSYNC source camera disconnects)

- Detection: MSYNC heartbeat missing for >2 s.
- Behaviour: promote one of the slaves to master; re-broadcast. Anchor freshly via audio xcorr on the next shot.
- This is a measurable but small accuracy event — we may see one shot of higher uncertainty until re-anchored.

### 7.5 Both cameras' audio missing simultaneously

- Causes: powered USB hub failure, both Media Mods unplugged, range PA covering the muzzle blast (rare).
- Behaviour: MSYNC-only sync, prominent report annotation, suggest operator check audio chain at next string break.

---

## 8. Test Rig Requirements

Sync code must be testable without real hardware. Sprint 17 (firmware review §"Mock/Fixture Improvements") depends on this.

### 8.1 Synthetic 2-camera mock

The mock camera (`aimvision-camera-mock` crate, see `docs/camera-integration-spec.md` §12) supports clock-skew injection per camera:

```yaml
cameras:
  - id: cam_a
    clock:
      offset_ms: 0
      drift_ppm: 0
      jitter_pdf: gaussian(mean_ms=0, stddev_ms=0.5)
  - id: cam_b
    clock:
      offset_ms: 12.7 # constant offset
      drift_ppm: 8 # 8 ppm linear drift = ~29 ms / hr
      jitter_pdf: gaussian(mean_ms=0, stddev_ms=0.8)

shots:
  - t: 5.0 # ground-truth absolute time
    audio_amplitude: 0.92
    transient_rise_ms: 0.4
  - t: 12.3
    audio_amplitude: 0.85
    transient_rise_ms: 0.5
  # ...
```

The mock camera framework synthesises:

- A per-camera audio stream with the configured impulses + ambient noise (configurable SNR; 18 dB SNR baseline).
- Per-camera frame PTS values offset and drifted as configured.
- An MSYNC broadcast with the configured ground-truth-vs-broadcast offset.

### 8.2 CI assertions

The CI sync test suite asserts:

1. Per-shot offset recovery within **±1 ms** of ground truth across the configured jitter PDF.
2. Drift compensation between shots within **±2 ms** for a 60-shot session.
3. Failure-mode tests (audio anchor missing on alternating shots) pass without exceeding ±5 ms degradation.
4. Recovery after master-clock dropout completes within 3 shots.

### 8.3 Why this exists before hardware

Real federation hardware lands in Sprint 17 (firmware review timeline). Without the synthetic test rig, sync code lands in Sprint 17 _and_ gets validated in Sprint 17 — a 2-week sprint becomes 8 weeks. With the synthetic rig from Sprint 8, sync code lands and is validated in CI by Sprint 12; Sprint 17 is hardware-validation only, fits in 2 weeks.

### 8.4 Real-hardware bring-up

Once federation hardware arrives:

1. Run the same shot-timeline through real cameras + golden audio.
2. Compare CI-synthetic-rig recovered offsets vs. real-hardware recovered offsets.
3. Any divergence >1 ms is a CI-fixture bug, not a code bug — update the synthetic model.

---

## 9. V1 Scope

Per Sprint Prioritizer review:

- **V1 ships:** single-camera Solo + Club tiers. Federation tier is **architecture-only** — the schema, traits, and `aimvision-camera-mock` 2-camera test rig are in place, but no public federation 2-camera SKU.
- **V1.5 ships:** federation 2-camera with full multi-cam sync validation against real hardware. ChArUco calibration, MSYNC + audio xcorr, drift compensation all on.
- **V2:** federation 3-camera + VoxelPose 3D pose pipeline + USB-C HID hardware trigger investigation.
- **V3:** custom AIMVISION hardware with true hardware genlock; deprecates !MSYNC dependency.

V1's responsibility is to **make V1.5 a 2-week sprint**, not to ship federation. That happens through:

1. Per-shot, per-camera sync fields in the `Recording` schema (§5).
2. The `aimvision-camera-mock` synthetic 2-camera rig with deterministic CI (§8).
3. The `CameraCapabilities::supports_msync()` flag on the trait surface.
4. Calibration data structures wired into the local event store but unused on Solo / Club.
5. A documented `!MSYNC` integration path in the GoPro client crate, behind a `feature = "labs"` gate.

If we ship V1 without these, Sprint 17 is an architectural rework. If we ship V1 with these, Sprint 17 is a configuration toggle and a hardware bring-up.

---

## Appendix A: Acronyms

- **DLT** — Direct Linear Transform
- **GPMF** — GoPro Metadata Format
- **MSYNC** — Open GoPro Labs precision time-sync command
- **MvP** — Multi-view Pose Transformer
- **NPU** — Neural Processing Unit
- **PDF** — Probability Density Function (in §8 context — not the document format)
- **PnP** — Perspective-n-Point (camera pose estimation)
- **PTS** — Presentation Time Stamp
- **RTMPose** — Real-Time Multi-person Pose estimation (OpenMMLab)
- **SNR** — Signal-to-Noise Ratio
- **TDOA** — Time Difference Of Arrival

## Appendix B: References

- Open GoPro Labs documentation — `https://gopro.github.io/labs/control/extensions/#msync`
- OpenCV ChArUco calibration — `https://docs.opencv.org/4.x/df/d4a/tutorial_charuco_detection.html`
- Ceres bundle adjustment — `http://ceres-solver.org/nnls_tutorial.html#bundle-adjustment`
- VoxelPose — Tu et al., "VoxelPose: Towards Multi-Camera 3D Human Pose Estimation in Wild Environment," ECCV 2020
- MvP — Wang et al., "Direct Multi-view Multi-person 3D Pose Estimation," NeurIPS 2021
- RTMPose — `https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose`
- `docs/camera-integration-spec.md`
- `docs/reviews/05-embedded-firmware-engineer.md` §"Multi-Camera Sync Recommendation"
- `docs/reviews/10-performance-benchmarker.md`
