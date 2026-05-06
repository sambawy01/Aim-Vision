# AIMVISION ML Architecture

**Owner:** AI Engineer
**Date:** 2026-05-06
**Status:** v1.1 — supersedes the ML sections of `AIMVISION_V1_Sprint_Build_Plan.txt`
**Sibling specs:** `docs/diagnostic-taxonomy.md`, `docs/llm-coaching-notes-schema.md`, `docs/multi-camera-sync-spec.md`, `docs/performance-budgets.md`
**Reviews this revises:** `docs/reviews/01-ai-engineer.md`, `docs/reviews/05-embedded-firmware-engineer.md`, `docs/reviews/08-ux-researcher.md`, `docs/reviews/10-performance-benchmarker.md`

---

## 1. Product context and ML problem framing

AIMVISION coaches clay/skeet shooters. The athlete fires; the system tells them why they hit or missed, in language a coach would actually use, and tracks the pattern of why over weeks. Three fundamentally different latency/accuracy regimes share one feature store and one taxonomy:

1. **Live tier (on-device, latency-bound).** From muzzle blast to a feed entry on the phone: **p50 ≤ 2.5 s, p95 ≤ 4 s on Wi-Fi; p50 ≤ 1.2 s on USB-C**. The shot-to-feed entry is decoupled — show "Shot detected" within 800 ms via the audio path, then back-fill the diagnostic line within the budget. This is the "perceived latency" trick from `docs/reviews/10-performance-benchmarker.md`. Live diagnostics use distilled models running on Apple Neural Engine / Android NNAPI/QNN. Accuracy is secondary to responsiveness here; the live tier flags candidates that the post-session tier confirms.

2. **Post-session tier (backend GPU, accuracy-bound).** A 30-min, ~80-shot session produces the report in **p50 ≤ 90 s, p95 ≤ 150 s, hard cap 180 s with a degraded fallback**. Runs full-resolution pose, temporal action detection, multi-task diagnostic ensemble, RAG-grounded LLM coaching note, PDF render. Target hardware is a single A10G or L4 (T4 is too slow for HRNet-class models per the perf review). 32B LLM does not fit the budget on A10G — use 14B Q4_K_M.

3. **Longitudinal tier (offline, cohort-aware).** Bayesian structural time-series per athlete, regime-change detection, per-athlete LoRA personalization after ~200 shots. Detects "developing fault" vs. "bad day". Runs nightly per active athlete; not on the live or post-session critical path.

The input is **multimodal**: video (Hero 13), audio (Media Mod or USB-C UVC PCM), and — committed to V1 P1 in this revision — **gun-stock IMU @ 200 Hz over BLE**. V1.5 candidates: 4-mic camera-mount array for TDOA shot localization, phone front-cam for gaze and head-pose. The single biggest architectural decision in this doc is to elevate IMU from V2 to V1 P1: it is the cheapest, highest-impact accuracy lever (`docs/reviews/01-ai-engineer.md` "Accuracy improvements" rank 1).

---

## 2. Sensor stack v1 (revised)

### Hero 13 video
- **Live preview:** UDP MPEG-TS H.264, ~480p30, documented 1–2 s floor of latency (`docs/reviews/05-embedded-firmware-engineer.md`). This is the floor, not the goal. Federation tier must use **USB-C UVC tether** at 1080p with ~200–400 ms latency; the perf review correctly upgrades this from P1 to P0 for federation.
- **Recorded:** 4K60 H.265 to SD card, GPMF metadata for camera IMU and timecode, retrieved post-session for the accuracy-bound pipeline.

### Hero 13 audio
- **Default:** Media Mod cardioid electret, 48 kHz mono, AAC inside MP4. AAC adds 20–40 ms encoder latency that matters for sub-shot timing.
- **Recommended upgrade:** **USB-C UVC raw PCM** if the Hero 13 firmware path supports a UAC audio class endpoint over the same USB-C tether used for video. This eliminates the AAC decode and gives clean 16-bit @ 48 kHz to the shot detector. Embedded review flags this as "capture raw PCM via UVC if possible" — confirming this in firmware bring-up is a Sprint 4 deliverable.
- Foam windscreen as a hardware SKU; wind above 15 km/h dominates the Media Mod.

### Gun-stock BLE IMU — promoted to V1 P1
- **Part:** **BMI270** preferred (lower power, better noise floor than MPU-6050; ~$3 in volume, ~$15 finished BOM with case + battery + nRF52). MPU-6050 is the fallback if BMI270 supply slips.
- **Rate:** 200 Hz 6-axis (accel + gyro), tap-detect interrupt for shot timing.
- **Form factor:** Mantis-style stock clamp; user-removable; survives 30–50 G recoil.
- **Why now (not V2):** sub-10 ms shot timing fusion with audio; ground-truth swing velocity, mount jerk, recoil signature; resolves stopped-gun/head-lift ambiguity directly with a kinematic signal the camera physically cannot recover.
- **Owned by:** Embedded firmware, but ML owns the fusion model and time-alignment protocol.

### 4-mic camera-mount array (V1.5 candidate)
- Resolves multi-shooter audio interference (Risk R7) via TDOA beamforming. Embedded review: "two shooters firing within 1.5 sec on adjacent stations will produce overlapping transients that a simple threshold detector will merge." Without this, the audio detector is unreliable at competitive ranges.
- ~$30 BOM; mounts on the existing camera tripod plate.

### Phone front-cam gaze + head-pose (V1.5 candidate)
- **Why it's the most coachable variable in skeet:** gaze leads head leads gun by 80–150 ms, published in shooting-sports biomechanics. Detecting head-lift before the gun has even moved is a step-change in coaching latency.
- Models: 6DRepNet or WHENet (head-pose), L2CS-Net (gaze).
- Costs nothing in hardware (phone is already there) but costs UX surface area, so it's V1.5 not V1.

---

## 3. Live on-device pipeline

End-to-end on-device flow, anchored on audio:

```
mic PCM ─► audio shot detector (CRNN, 50ms hop / 200ms window)
                │
                ▼
         shot event ◄──── BLE IMU tap-detect (sub-10ms) ── fusion gate
                │
                ├─► pose @ 8-12 fps (RTMPose-Lite, distilled)
                │
                ├─► barrel @ 5-8 fps (YOLOv8n int8)
                │
                └─► diagnostic MLP (per-shot, fires on shot event)
                │
                ▼
         feed entry (audio-first preview within 800ms,
                     diagnostic back-fill within budget)
```

**Runtime:** ONNX Runtime Mobile with Core ML EP on iOS, NNAPI EP on Android (QNN/Hexagon EP where available, e.g., S22). All four models compiled int8 where it doesn't cost macro-F1 > 1 point on the validation set.

**Backpressure (single mpsc, `try_send`, per-stage drop counters):**
1. Drop pose first.
2. Drop barrel YOLO second.
3. Never drop audio. Never drop preview decode.

**Audio chunking:** 50 ms hop, 200 ms window — perf review's recommendation. 10 ms hop is overkill (cost > latency win); 100 ms loses double-shot disambiguation.

**Thermal degradation ladder (mirrors perf review):**
- 42 °C → pose to 5 fps
- 44 °C → drop barrel YOLO entirely
- 46 °C → preview to 12 fps
- 48 °C → audio-only mode + banner

Cite `docs/performance-budgets.md` for the per-stage histograms (p50/p95/p99 for `audio_detect`, `pose_infer`, `yolo_infer`, `classifier`, `bridge`, `shot_to_feed`). OpenTelemetry span per stage from Sprint 6 — non-negotiable.

---

## 4. Pose model decision

**Replace MediaPipe BlazePose.** It's trained on yoga/fitness and degrades on lateral and oblique stances (skeet stations 1 and 7), has 33 keypoints with no hand articulation, and has no gun-relevant landmarks. MediaPipe was a starter choice; it is the wrong model for this sport.

**Decision:**
- **Post-session (accuracy-bound):** **RTMPose-x** (MMPose) with **MMPose Wholebody** topology — 133 keypoints including hands and face. Hand articulation is needed for trigger-finger detection; face landmarks are needed for cheek-weld and dominant-eye. ViTPose-H is a credible alternative on the same topology; we choose RTMPose-x because the inference path on A10G is faster and the ONNX export is more stable. Re-evaluate at Sprint 18 if MMPose ships an improved ViT distillation.
- **Live (latency-bound):** **RTMPose-Lite** distilled from RTMPose-x on our own data. We do not run Wholebody at 8–12 fps on phone — we run a 17-keypoint COCO topology live and recover the hand/face keypoints in the post-session pass. The live diagnostic head only consumes signals the COCO topology supports (head/torso/arm angles); cheek-weld and trigger-finger are post-session only.

**Justification — beyond `docs/reviews/01-ai-engineer.md`:** lateral skeet stations are where MediaPipe's COCO-fit fails worst; cheek-weld is the highest-signal head/eye fault and requires face landmarks; dominant-eye landmark is impossible without face mesh; trigger-finger faults need hand keypoints.

---

## 5. Barrel and clay tracking

**Barrel detection.**
- **Live:** YOLOv8n int8 quantized at 5–8 fps. Tooling maturity > marginal accuracy of RTMDet/NAS variants. Subsampled, not every frame.
- **Post-session:** **SAM2** mask propagation initialized from a YOLOv8x detection. Once the gun occludes the torso during mount, a bbox is the wrong primitive — a mask handles partial occlusion of barrel-by-hand and barrel-by-torso cleanly. This is the AI review's recommendation and we adopt it.

**Clay tracking.**
- **ByteTrack** anchored on YOLOv8 detection. ByteTrack > OC-SORT for our case because clays have low ID-switch rate (single track per shot, predictable trajectory) and ByteTrack's track-by-detection-association is simpler to debug. OC-SORT remains a fallback if Kalman fails on shot-debris occlusion.

---

## 6. Multi-camera 3D pose (Federation tier)

Federation rigs use 2–3 cameras. We recover 3D keypoints via **VoxelPose** (volumetric, robust to per-view detection error) or **MvP — Multi-view Pose Transformer** (faster, learned association). Default to VoxelPose; fall back to MvP if inference time exceeds budget at 3-camera setups.

**Calibration:** ChArUco boards (12×9), survives partial occlusion when athletes walk through frame. OpenCV `calibrateCamera` for intrinsics + `solvePnP` for extrinsics, refined with **Ceres bundle adjustment**. Expected reprojection error: **2–3 mm at 5 m baseline** (`docs/reviews/05-embedded-firmware-engineer.md`).

**Sync:** hybrid Open GoPro Labs `!MSYNC` (coarse, ~5–15 ms) + audio cross-correlation on the muzzle blast (sub-millisecond per shot). Record `camera_clock_offset_ms` per camera per shot in the Recording entity schema. Cite `docs/multi-camera-sync-spec.md`.

3D unlocks real swing-plane geometry, head-stock alignment in absolute degrees, and lead distance estimation when fused with clay tracks. Without 3D this is impossible from a monocular GoPro — that's an AI-review correction we accept and bound.

---

## 7. Temporal action detection (post-session)

Mount, swing, and follow-through are sequential by construction. Static per-frame features throw away the signal.

**Backbone:** **VideoMAE-v2** (preferred) or **InternVideo2**, **frozen** in V1 — we don't have the labels to fine-tune end-to-end and we don't need to. Frozen embeddings on shot-clip windows feed downstream heads. We pretrain via masked autoencoding on our own raw shooting footage (see §10).

**Heads:** **ActionFormer** for boundary detection of mount-start, gun-up, break-point, follow-through-end on each ±2 s shot clip. **TriDet** is the fallback if ActionFormer's training is unstable on small data.

**Why this matters:** the AI review puts this as the single biggest accuracy move available. Boundaries are also what powers "notable shot" selection in the LLM coaching note (§11) and the `evidence_shot_ids` field in `docs/llm-coaching-notes-schema.md`.

---

## 8. Diagnostic head — multi-task, hierarchical, multi-label, calibrated

**Structure (DAG, not flat multiclass):**

```
shared embedding (pose + IMU + audio + VideoMAE clip features)
    │
    ├─► head/eye expert ───────┐
    ├─► mount/stance expert ───┤
    ├─► swing/lead expert ─────┤──► meta-classifier ──► outcome + cause attribution
    └─► follow-through expert ─┘
                                      ▲
                                      │
                              structured prior:
                              stance → mount → swing → break → outcome
```

Each expert produces **calibrated probabilities** for its own taxonomy branch. The branches and atoms are defined in `docs/diagnostic-taxonomy.md`. They are **multi-label**: head-lift, stopped-gun, and off-line co-occur regularly. A single multiclass head is structurally wrong here — that's an AI review correction we accept verbatim.

**Calibration.**
- **Per-task temperature scaling** (Guo et al. 2017) on a held-out set per expert.
- Report **Expected Calibration Error (ECE)** and **Brier score** per class. Target ECE ≤ 0.05 per task.
- **Conformal prediction** (Angelopoulos & Bates) yields per-shot prediction sets with 90% coverage. Prediction sets are surfaced honestly in the UI as "likely cause + alternates" rather than as a fake top-1.

**Abstention.**
- **Per-class thresholds.** Head-lift is easier to detect than stopped-gun — global thresholds under-fire on easy classes and over-fire on hard ones. Tuned on stratified validation.
- UX-review constraint: "cause unclear" budget is **15% of shots maximum**. Above that the live feed reads as broken. The taxonomy spec defines a low-confidence-best-guess presentation that keeps abstention at ≤ 15% while preserving epistemic honesty (`docs/diagnostic-taxonomy.md` §Meta).

---

## 9. IMU fusion for ground-truth swing kinematics

**Time alignment.** Audio shot detector and IMU tap-detect interrupt fuse to **sub-10 ms** shot timing. The IMU's onboard tap-detect pulls down a GPIO that the nRF52 timestamps against its BLE-disciplined clock, broadcast every 100 ms. Fusion logic on phone: take audio peak ± 50 ms, find nearest IMU tap, accept if within window, else treat as a missed-mic shot (camera muffled, wind) or missed-tap shot (low-recoil low-gauge round).

**Kinematic features available from the IMU:**
- Swing angular velocity (gyro-Z primary, gyro-Y secondary for vertical lead).
- Swing angular acceleration (numerical derivative, low-pass filtered).
- Mount jerk (third derivative of accel-Y; spike during mount).
- Recoil signature (accel-X impulse profile; gauge-dependent template match).
- Barrel orientation (Madgwick or Mahony AHRS, ~2° steady-state drift over 30 s; re-anchored each shot via gravity-vector reset between shots).

**Resolves directly:**
- **Stopped-gun:** angular velocity drops below threshold within 100 ms before muzzle blast → kinematic ground truth. Today this is inferred from pose with high error.
- **Head-lift vs. stopped-gun ambiguity:** if angular velocity is healthy and pose-derived head-stock angle increases pre-shot, it's head-lift, not stopped-gun. Without IMU these are confusable.
- **Mount jerk magnitude:** quality-of-mount metric independent of pose.

**Mantis form-factor precedent** (Mantis X3/X10 ship the same primitive for rifle/pistol training; the engineering is well-trodden).

---

## 10. Training strategy

### Self-supervised pretraining
**VideoMAE-v2 masked autoencoding** on all raw shooting footage we record, **including footage we don't have labels for**. Mask ratio 75%, tube masking, 16-frame clips. This is the single largest label-efficiency lever — expect **5–10× fewer labels** for a given downstream accuracy. We also pretrain on near-domain action data (HMDB-51, Kinetics-400 sports subset) for the first epoch, then domain-shift onto our own footage.

### Weak supervision
**Audio shot timestamps auto-segment** ±2 s clips. Hit/miss outcome from the GoPro Hilight tag (when present) and from clay-tracker disappearance event (when not). This generates millions of weakly-labeled clips for free. Diagnostics still need expert labels, but clip boundaries do not.

### Active learning
**BALD acquisition** (Bayesian Active Learning by Disagreement) over the diagnostic ensemble; **coreset selection** as a fallback that doesn't depend on ensemble disagreement quality. The active-learning queue prioritizes the highest-uncertainty shots for **Franco** and a small panel of expert coaches. UX review: "Don't burn Franco on labels." This is how we don't.

### Per-athlete LoRA personalization
After ~**200 shots** per athlete we fine-tune a **LoRA adapter** on the diagnostic heads only (rank 8, alpha 16). Mitigates the Egypt-cohort domain shift the AI review flags, and creates per-athlete lock-in (the model is materially better for you the longer you use it). The base model is shared; only the adapter is athlete-private.

### Continual learning + provenance
Every training sample carries `(athlete_id, session_id, source, captured_at, consent_flags)`. **Minor-data ML-training opt-out is the default** (per Compliance review). Re-training jobs filter on consent flags at the data-loader layer, not at the application layer; this is a compliance hard requirement, not a feature toggle.

---

## 11. LLM coaching notes pipeline

**Model:** **DeepSeek 14B Q4_K_M via self-hosted Ollama** on A10G. 32B is not viable (50 s+ on A10G per perf review; H100 is cost-prohibitive at our SKU price). Re-evaluate when DeepSeek V5 ships or when we move to L40S/H100 for federation tier.

**RAG.** Per-athlete retrieval over the **last 5 sessions of coaching notes** for that athlete. Embeddings: bge-large-en-v1.5 → Qdrant. Top-k=8, reranked with bge-reranker. The point is **style continuity** — Franco's notes for athlete A read like Franco's notes for athlete A, not generic shooting advice.

**Fine-tuning.** **LoRA adapter on Franco-corrected outputs**, collected via the UI override loop. The athlete-app override surfaces are also training data sources; UX review: "Override = signal, not failure." Weekly fine-tune cadence; deploy via MLflow Model Registry (§13) with shadow eval before promotion.

**Structured output.** **Outlines** (preferred) or **Guidance** for grammar-constrained decoding against the JSON Schema in `docs/llm-coaching-notes-schema.md`. Free-form text is hallucination-prone; constrained decoding eliminates whole classes of failure (wrong field names, missing required fields, drill_id references that don't exist in the drill library).

**Verifier pass.** After generation, a **second LLM call** receives the structured note and the underlying feature vector, and answers: "do the cited features in `top_diagnostics` actually match the data?" If verifier returns false, regenerate (max 2 retries) then return a degraded note (no top_diagnostics, just headline + drill recommendations).

**Privacy.** Athlete name and direct identifiers are **stripped before prompts** and replaced with stable per-session pseudonyms (e.g., "Athlete-7421"). Cite Security review. The LLM never sees PII.

---

## 12. Evaluation rigor

**Inter-annotator agreement.** Cohen's κ between Franco and ≥ 2 additional expert coaches on a fixed eval set of 500 shots. Expected κ in **0.6–0.75** for diagnostics (AI review). **That is the ceiling, not 100%** — the marketing target of "85% accuracy" is meaningless above the inter-rater ceiling.

**Stratified eval.** Per-station, per-discipline (skeet/trap/sporting), per-lighting (good/harsh-sun/dust), per-body-type, per-skin-tone, per-clothing color (orange high-vis vs. black). Bias gaps that exceed 5 macro-F1 points across any axis fail the bias audit.

**Bias audits as a CI gate.** Not a quarterly review. Every model promotion runs the stratified eval; the bias audit blocks promotion if any axis fails. Owner: AI Eng + Compliance review sign-off.

**Targets (restated, with denominators).**
- Diagnostic top-3 macro-F1 ≥ **0.78** on the stratified test set.
- Outcome (hit/miss) detection ≥ **95%** in good lighting, ≥ **88%** in harsh sun.
- Calibration **ECE ≤ 0.05 per task**.
- Inter-rater-normalized accuracy ≥ **0.92 × κ_ceiling** (i.e., the model gets 92% of the way to the human-human agreement ceiling).

**Wizard-of-Oz baseline.** Per UX review, Franco hand-writes coaching notes from 30 sample sessions in three formats before we build the LLM pipeline. A/B against athletes for "did you act on it?". This pins the LLM target to a real coaching artifact, not a synthetic benchmark.

---

## 13. Model registry and shadow evaluation

**MLflow Model Registry** for every model: pose, barrel YOLO, audio shot detector, each diagnostic expert, meta-classifier, ActionFormer, LLM LoRA adapters.

- **`model_version` column on every prediction** in the database. Forever. This is non-negotiable; it's how we attribute regressions and run retrospectives.
- **5% shadow routing** of a candidate model alongside production. Predictions stored separately; never surfaced to athletes.
- **Win condition:** candidate beats production on stratified macro-F1 by ≥ 0.01 AND does not regress any single class by > 0.02 AND passes the bias-audit gate AND passes the calibration gate.
- **Auto-promote** on win threshold sustained over 2 weeks (or ~1000 production shots, whichever is later). Manual promote gate for any model that touches the LLM pipeline (Franco signs off in writing).
- **Rollback:** instant, single-flag in the registry. Test the rollback path quarterly.

---

## 14. Backend post-session pipeline budget

From `docs/performance-budgets.md`, copied here for reference:

| Stage | Budget | Reality on A10G |
|---|---|---|
| Video re-fetch from object storage (4 GB @ 1 Gbps) | 8 s | 10–15 s; 5 s with CloudFront edge |
| Re-decode + frame extraction (every 6th frame, 30 min) | 12 s | 8–15 s with NVDEC |
| Full-res pose (RTMPose-x @ ~10 fps GPU) | 25 s | 20–30 s on A10G |
| Audio re-detection (Whisper-tiny + custom CRNN) | 5 s | 3–8 s |
| Per-shot diagnostic ensemble (~80 shots) | 8 s | 6–12 s |
| Pattern detection + aggregation | 3 s | 2–5 s |
| **DeepSeek 14B Q4_K_M coaching notes (~600 output tokens)** | **18 s** | **14–22 s @ ~35 tok/s on A10G** |
| PDF render | 3 s | 2–4 s |
| **Total p50** | **82 s** | **65–110 s** |

**SLA: p50 ≤ 90 s, p95 ≤ 150 s, hard cap 180 s.** On hard-cap breach, **degraded fallback**: skip VideoMAE pass, generate a lighter coaching note from per-shot features only, mark the report as `degraded=true` in the schema. This is reported to the user honestly ("full analysis didn't finish in time; here's what we have").

**Hardware:** A10G or L4 minimum per worker. T4 is too slow for RTMPose-x. Auto-scale workers from a queue; backend ML worker pool design owed by Sprint 11 — don't wait until Sprint 22 (perf review).

---

## 15. Edge cases and robustness

- **Multi-shooter audio interference.** TDOA mic array (V1.5). In V1 we fall back to **IMU tap-detect as the primary shot anchor** when audio confidence is low — IMU is immune to neighboring shooters. Post-session re-detection uses both signals jointly.
- **Bright sunlight, glare on orange clays.** Polarized clay-paint during pilot; CPL filter on Hero 13 lens (it accepts threaded mods, embedded review). Augmentation in training: aggressive exposure, white-balance, glare-spot synthesis. Bias-audit axis includes lighting.
- **Camera thermal shutdown.** Graceful inference degradation ladder (§3); when the camera derates from 4K60 to 2.7K30, post-session pose runs on the lower-res input and we accept a documented accuracy hit (calibration constants per resolution stored in the model registry).
- **Network outage.** Offline inference parity — all live-tier models run on-device, no cloud dependency for the live feed. Sync on reconnect. Post-session pipeline is cloud-only and acknowledged: "report will generate when you're back online."
- **Forgot-to-pause / dead time.** Auto-detect: > 5 min without a shot AND idle pose. Offer "Trim 14:32 of inactivity?" before report generation (UX review gap #4). Pre-session pipeline trim is computed before the 90 s budget starts.
- **GoPro died at shot 47.** Audio-only mode continues recording (phone mic fallback). Report distinguishes: "47 of ~100 shots with full diagnostics; 53 audio-only." This is an explicit `partial_session=true` flag in the schema, not a broken report.

---

## 16. Smarter-feature roadmap (V1.5 candidates, ranked)

1. **Phone front-cam gaze + head-pose.** Highest coaching-leverage feature on the roadmap; gaze leads gun by 80–150 ms.
2. **4-mic TDOA shot-localization array.** Resolves multi-shooter audio at competitive ranges; required for federation tier.
3. **Gun-stock IMU as a productized SKU** (rather than an early-adopter optional accessory). Embedded firmware engineer should spec the certified version once V1 BMI270 prototype is validated in Egypt.
4. **Bayesian structural time-series** for the longitudinal tier — replaces rolling-window pattern detection with regime-change detection that has proper uncertainty.
5. **Multi-camera 3D pose** at the prosumer tier (V1 is federation-only). Requires the ChArUco calibration kit to ship as an SKU.

---

## 17. What is explicitly NOT being built in V1

- **Eye-tracking glasses.** Latency to FDA/CE compliance and athlete acceptance kills it for V1. Phone front-cam gaze is the V1.5 substitute.
- **Generic action-recognition pretraining from scratch.** We pretrain VideoMAE on our footage and reuse public weights for the first epoch. We do not train a new sports backbone from zero.
- **On-device VideoMAE inference.** Too heavy for phone NPUs at any sensible accuracy. VideoMAE is post-session only.
- **Per-shot 3D pose from monocular video.** Physically impossible without depth or multi-view; the V1 plan promised it implicitly and we are explicitly not promising it. 3D is federation-tier only.
- **End-to-end neural shot diagnostician trained from raw pixels.** Hierarchical multi-task heads with engineered + learned features beat a single end-to-end model on label efficiency at our data scale. Revisit at >100k labeled shots.

---

**Sign-off owners:** AI Eng (this doc), Embedded (sensor stack §2 + IMU §9), Performance (§3 budgets + §14 budgets), Compliance (§10 consent flags + §11 PII stripping), UX (§12 vocabulary card-sort dependency).
