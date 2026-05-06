# AIMVISION Performance Budgets and SLAs

**Owner:** Performance Benchmarker
**Status:** Canonical (supersedes all latency/battery/thermal/capacity numbers in `AIMVISION_V1_Sprint_Build_Plan.txt` v1.0)
**Last reviewed:** 2026-05-06
**Cited reviews:** `docs/reviews/04-mobile-app-builder.md`, `docs/reviews/05-embedded-firmware-engineer.md`, `docs/reviews/10-performance-benchmarker.md`

---

## 1. Why this exists from Sprint 3, not Sprint 19

Battery, thermal, and end-to-end latency are not polish — they are **architectural decisions** that pin every layer of the stack:

- **Battery** dictates whether ML runs on ANE/NNAPI/QNN (mandatory) versus CPU (non-viable). It dictates whether we hardware-decode H.264 (mandatory) versus software-decode (35%/hr drain). It dictates whether the Skia overlay path is GPU-composited (mandatory) versus CPU canvas. Get this wrong in Sprint 5 and the whole frame pipeline must be rebuilt in Sprint 19.
- **Thermal** dictates whether the Hero 13 runs at 4K or 2.7K, whether the camera ships with a white silicone sleeve, and whether the operator phone needs an active-cooled USB-C dock for the federation tier. These are hardware SKU decisions, not software flags.
- **Latency** dictates whether the federation tier requires USB-C UVC tethering (it does — see Section 2). Wi-Fi alone cannot meet a sub-1.5s p50, so deferring the measurement defers the architectural fork.

The Sprint 19 (Egypt validation) plan in V1 reads "measure battery and thermal." That is six months too late. By Sprint 19 the architecture is locked, the hardware SKUs are picked, and the only remaining lever is "ship slower" or "ship worse." This document moves all targets to **Sprint 3** so they constrain Sprint 4-18 instead of judging them.

Reviewer verdict (`10-performance-benchmarker.md`): **Battery/thermal deferral to Sprint 19 is the single biggest performance risk in the plan.** This document closes that gap.

---

## 2. Live coaching feed SLA — restated honestly

The V1 plan states "1-3s feed latency" as a single number. That is not a SLA — it is a wish. A SLA must specify percentile, network path, and degradation behavior. The honest spec:

### 2.1 Wi-Fi path (default mobile, Hero 13 5GHz AP)

| Metric                     | Target                                                                                        |
| -------------------------- | --------------------------------------------------------------------------------------------- |
| Shot-to-feed-entry p50     | **≤ 2.5s**                                                                                    |
| Shot-to-feed-entry p95     | **≤ 4s**                                                                                      |
| Hard cap                   | **6s** — beyond this, surface a degraded UI banner: "Live feed delayed — recording continues" |
| Glass-to-glass preview p50 | ≤ 1.1s                                                                                        |
| Glass-to-glass preview p95 | ≤ 1.8s                                                                                        |

### 2.2 USB-C tethered (federation tier, Hero 13 UVC mode)

| Metric                     | Target     |
| -------------------------- | ---------- |
| Shot-to-feed-entry p50     | **≤ 1.2s** |
| Shot-to-feed-entry p95     | **≤ 2.0s** |
| Glass-to-glass preview p50 | ≤ 350ms    |
| Glass-to-glass preview p95 | ≤ 600ms    |

USB-C UVC tethering moves from V1 plan's Sprint 7 [P1] to **Sprint 7 [P0] for the federation tier**. It is the only credible path to sub-1.5s p50 (see `05-embedded-firmware-engineer.md` Section "Open GoPro Reality Check").

### 2.3 Perceived-latency decoupling

The audio shot detector is on the critical path; the visual diagnostic is not.

- **Audio path fires "Shot detected" feed entry within 800ms p95.** This is the user-perceived latency that matters.
- **Visual diagnostic (pose/barrel/MLP) back-fills the feed entry within 2s p95** with the swing-line, lead value, and break-point assessment.

This is not optional. It is the only way the Wi-Fi p50 of 2.5s feels acceptable. The athlete sees a row appear in <1s; the coach sees the diagnostic detail by the time they look at the screen.

### 2.4 The original V1 "1-3s" SLA is replaced

The V1 plan's "1-3s on Wi-Fi" is unachievable at p95 given documented GoPro Hero 11/12 preview floor of 1.0-1.5s on a clean radio environment, 2-3s with interference. Hero 13 has not been independently benchmarked at the time of writing — assume parity until proven better. Adding ML, RN bridge, and render onto that floor produces a realistic Wi-Fi p50 of 1.8-2.5s and p95 of 3-4s. **This document supersedes the V1 SLA.**

---

## 3. Live latency budget table (per-stage, p50)

End-to-end stage budgets, p50, both network paths. Numbers extend the table in `10-performance-benchmarker.md` Section "Live Latency Budget Table" with a USB-C column.

| Stage                                         | Wi-Fi p50        | USB-C UVC p50   | Notes                                                    |
| --------------------------------------------- | ---------------- | --------------- | -------------------------------------------------------- |
| Hero 13 sensor → encoder                      | 80 ms            | 80 ms           | H.264 hardware encoder, identical both paths             |
| Hero 13 emit (Wi-Fi UDP / UVC USB)            | 320-520 ms       | 30-60 ms        | The dominant variance source on Wi-Fi                    |
| Radio / cable transit + jitter buffer         | 150-300 ms       | 5-15 ms         | Wi-Fi 5GHz outdoor; UVC isochronous                      |
| H.264 hardware decode (VT/MediaCodec)         | 30-50 ms         | 30-50 ms        | One-frame queue typical                                  |
| Frame copy → Rust core → tensor prep          | 20-40 ms         | 20-40 ms        | UniFFI/JNI marshal + color convert                       |
| Audio shot detection (50ms hop, 200ms window) | 30-50 ms         | 30-50 ms        | Independent path; gates "Shot detected" feed entry       |
| Pose inference (RTMPose-Lite, NPU)            | 30-50 ms         | 30-50 ms        | Subsampled to 8-12 fps; replaces MediaPipe per AI review |
| YOLOv8n int8 (barrel)                         | 40-80 ms         | 40-80 ms        | Subsampled to 5-8 fps                                    |
| Diagnostic MLP (post-shot, 30 features)       | 30-50 ms         | 30-50 ms        | Fires only on shot event                                 |
| Aggregation → JSI HostObject → Skia render    | 80-150 ms        | 80-150 ms       | RN bridge eliminated via TurboModule + JSI               |
| **Shot-to-feed-entry total p50**              | **~1.6-2.4 s**   | **~0.55-1.1 s** | Audio path dominates user perception                     |
| **Glass-to-glass preview p50**                | **~700-1100 ms** | **~250-400 ms** | Independent of shot pipeline                             |

**Source of truth:** RTMPose-Lite replaces MediaPipe BlazePose Lite on the recommendation of the AI review. Latency is comparable; accuracy on partial occlusion (athlete behind shotgun) is materially better.

---

## 4. On-device ML budget per device

Target latency p95 per stage, per supported device. Cells marked "—" indicate the device is below the V1 supported floor (see Section 14). Sprint 9 [P0] adds quantized "lite" variants for older devices.

| Model                                | iPhone 13 | iPhone 15 Pro | Pixel 6a | Pixel 8 | Galaxy A54 | Galaxy S22 | Galaxy S24 |
| ------------------------------------ | --------- | ------------- | -------- | ------- | ---------- | ---------- | ---------- |
| Audio shot detector (CRNN, 50ms hop) | 25 ms     | 18 ms         | 45 ms    | 30 ms   | 50 ms      | 30 ms      | 22 ms      |
| RTMPose-Lite (10 fps subsampled)     | 22 ms     | 14 ms         | 60 ms    | 38 ms   | 70 ms      | 35 ms      | 28 ms      |
| YOLOv8n int8 (barrel, 6 fps)         | 38 ms     | 26 ms         | 95 ms    | 55 ms   | 105 ms     | 50 ms      | 40 ms      |
| Diagnostic MLP (per-shot only)       | 18 ms     | 12 ms         | 25 ms    | 18 ms   | 28 ms      | 18 ms      | 15 ms      |
| IMU fusion (Hero 13 GPMF, 100Hz)     | 8 ms      | 6 ms          | 12 ms    | 9 ms    | 14 ms      | 9 ms       | 7 ms       |

**Acceleration backend per device:**

- **iPhone 13 / 15 Pro:** Core ML on Apple Neural Engine (ANE). MPS GPU fallback only on thermal throttle.
- **Pixel 6a:** NNAPI on Tensor G1 TPU. EdgeTPU delegate where applicable.
- **Pixel 8:** NNAPI on Tensor G3 TPU; faster ANE-equivalent than 6a.
- **Galaxy A54:** NNAPI on Exynos 1380. Slowest supported device — drives the lite-variant work in Sprint 9.
- **Galaxy S22 / S24:** Qualcomm QNN delegate on Hexagon DSP (S22 Snapdragon 8 Gen 1, S24 Snapdragon 8 Gen 3). QNN is materially faster than generic NNAPI on Snapdragon devices; the delegate selection is per-device.

**CPU inference is non-viable** for any of these models on any of these devices. If NPU/DSP/ANE is unavailable (driver issue, OS bug), the app falls back to a 5fps mode with audio-only diagnostic and surfaces a "reduced fidelity" banner.

---

## 5. Audio chunk size and backpressure

### 5.1 Audio chunking

- **Hop:** 50ms
- **Window:** 200ms
- **Sample rate:** 48 kHz mono PCM (raw, not AAC-decoded — AAC adds 20-40ms encoder latency that breaks sub-shot timing per `05-embedded-firmware-engineer.md`)
- **Source:** UVC audio over USB-C where available; Hero 13 Media Mod 3.5mm electret over Wi-Fi otherwise

10ms hop is overkill — latency win is negligible versus CPU cost. 100ms hop loses sub-shot temporal resolution for double-shot disambiguation (two shooters firing within 1.5s on adjacent stations). 50ms is the empirical sweet spot.

### 5.2 Backpressure ladder

A single mpsc channel between the camera I/O thread and the ML thread, sized at 4 frames + 8 audio chunks. `try_send` semantics — never block the producer.

**Drop priority (drop first → drop last):**

1. **Pose inference frames** — drop first. The eye does not perceive 12fps overlays on 24fps video as long as keypoints are flagged stale.
2. **YOLO barrel frames** — drop second. Barrel position decays gracefully; last-known position is acceptable for 200ms.
3. **Preview decode frames** — drop third. Visible stutter; only drop under sustained thermal/CPU pressure.
4. **Audio chunks** — **never drop.** Audio is the shot-detection critical path. If the audio pipeline is failing, the session is failing — surface an error, do not silently degrade.

### 5.3 Drop counters as metrics

Per-stage drop counters exposed as OTel metrics:

- `pose_frames_dropped_total{reason}` — reasons: `queue_full`, `thermal`, `inference_timeout`
- `yolo_frames_dropped_total{reason}`
- `preview_frames_dropped_total{reason}`
- `audio_chunks_dropped_total{reason}` — **alert P1 if this is ever non-zero in production**

These metrics are wired into the live debug overlay (see `observability-plan.md` Section 5) and into the synthetic load rig assertions (Section 13).

---

## 6. Battery targets

### 6.1 Targets

| Device           | Live session battery drain (preview + pose overlay, 50% screen brightness) |
| ---------------- | -------------------------------------------------------------------------- |
| iPhone 13        | **< 18% / hour**                                                           |
| iPhone 15 Pro    | < 14% / hour                                                               |
| Pixel 6a         | **< 22% / hour**                                                           |
| Pixel 8          | < 18% / hour                                                               |
| Galaxy A54       | < 24% / hour                                                               |
| Galaxy S22 / S24 | < 18% / hour                                                               |

A 90-minute session must not drain more than ~30% on the median supported device.

### 6.2 Required to hit these targets

These are **architectural prerequisites** — not optimizations to chase later:

- **Hardware H.264 decode** via VideoToolbox (iOS) / MediaCodec (Android). Software decode burns 35%+/hr alone.
- **ML on ANE / NNAPI / QNN.** CPU inference at 8-12 fps pose burns 25%/hr on its own.
- **Wi-Fi PSM (Power Save Mode) disabled during session.** PSM adds 50-200ms of jitter to UDP; we accept the battery hit. Re-enable between sessions.
- **Skia/Metal/Vulkan GPU overlay.** CPU canvas rendering at 24fps is a 15%/hr drain.
- **Background mode discipline:** when the operator phone is screen-off but the session is active (e.g., phone on tripod, coach watching another station), inference pauses but the audio detector and recording link remain active. This drops drain to ~6%/hr.
- **GPS to 1Hz sampling**, not the default 10Hz. We only need station coordinates, not athlete tracking.
- **BLE keepalive only when Wi-Fi is up;** otherwise the phone reconnects via BLE which we already have to handle (see `05-embedded-firmware-engineer.md` Section "Open GoPro Reality Check").

### 6.3 Measurement

Battery is sampled every 10 seconds via `UIDevice.batteryLevel` (iOS) and `BatteryManager` (Android), shipped to the backend via OTel (see `observability-plan.md` Section 7). The dataset built from Sprint 4 onward is the dataset Sprint 19 _analyzes_ — not the dataset it starts collecting.

---

## 7. Thermal targets

### 7.1 Phone thermal budget

**Sustained 60-minute live session at 35°C ambient (Egypt baseline) without throttling.** Phone CPU/GPU package temperature stays below **42°C** at the operator phone position.

Test rig: Sprint 8 synthetic load rig (phone-on-tripod replaying fixture session) runs in a thermal chamber set to 35°C for the nightly CI assertion. Pre-Sprint-8 manual test: outdoor session at solar noon, not lab simulation.

### 7.2 Graceful degradation ladder

Sampled via `ProcessInfo.thermalState` (iOS) and `PowerManager.currentThermalStatus` (Android) every 10 seconds:

| Trigger                   | Phone package temp | Action                                                                                                                                     |
| ------------------------- | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `.fair` → `.serious`      | 42°C               | Drop pose inference to 5 fps                                                                                                               |
| `.serious` sustained 30s  | 44°C               | Drop YOLO barrel entirely; keep audio + pose @ 5 fps                                                                                       |
| `.serious` → `.critical`  | 46°C               | Drop preview to 12 fps; keep audio + recording link                                                                                        |
| `.critical` sustained 30s | 48°C               | Audio-only mode; surface "thermal protection active" banner; recording continues; coaching feed degrades to "Shot N detected" entries only |

The banner is **non-dismissible** until thermal state recovers to `.fair`. The session continues recording — we never lose footage to thermal.

### 7.3 Hero 13 thermal envelope

Hero 11/12 documented to thermally shut down at 4K60 in ~25 minutes at 25°C ambient. Hero 13's improved management still derates in heat. Spec for Egypt:

- **Capture mode:** 2.7K30 for live preview + recording (not 4K). Federation tier may opt in to 4K with a 3-minute cooldown per 20 minutes constraint.
- **3-minute cooldown per 20 minutes** of continuous capture at 35°C+ ambient. Build into session pacing — not a software hack, a documented protocol.
- **White silicone sleeve mandatory** for outdoor club sessions. Black plastic body in direct Egyptian sun reaches 60°C+ surface temperature.
- **Canopy mount mandatory.** Camera lives in the shade of the stand canopy, not in direct sun. Phone too — operator phone in direct sun thermal-throttles in 8-12 minutes.
- **Hero 13 thermal-state poll** added to the `Camera` trait now (Sprint 4), exposed as `CameraEvent::ThermalWarning` / `ThermalCritical` per `05-embedded-firmware-engineer.md` Section "Trait Design Changes."

---

## 8. Post-session pipeline budget

### 8.1 Targets

- **p50 ≤ 90s**
- **p95 ≤ 150s**
- **Hard cap 180s** — beyond this, the pipeline degrades: skip the VideoMAE pass, ship the report with a lighter coaching note, surface "Quick report — full analysis available in 5 min" to the user. Background a follow-up job to back-fill the full report.

These targets assume a 30-minute session, ~80 shots, and an A10G or L4 GPU worker. T4 is too slow for full-res HRNet — budget A10G/L4 minimum.

### 8.2 Stage table

Per-stage budgets, p50, on T4 vs A10G vs L4 vs H100.

| Stage                                                 | Budget   | T4 reality    | A10G reality        | L4 reality   | H100 reality |
| ----------------------------------------------------- | -------- | ------------- | ------------------- | ------------ | ------------ |
| Video re-fetch from object storage (4 GB)             | 8 s      | 10-15 s       | 5-8 s w/ CloudFront | 5-8 s        | 4-7 s        |
| Re-decode + frame extraction (every 6th frame, 30min) | 12 s     | 18-25 s       | 8-15 s w/ NVDEC     | 8-14 s       | 5-10 s       |
| Full-res pose (HRNet-W32 @ ~10 fps GPU)               | 25 s     | 50-80 s       | 20-30 s             | 22-32 s      | 8-14 s       |
| Audio re-detection (Whisper-tiny + custom CRNN)       | 5 s      | 6-10 s        | 3-8 s               | 3-8 s        | 2-5 s        |
| Per-shot diagnostic ensemble (~80 shots)              | 8 s      | 10-15 s       | 6-12 s              | 6-12 s       | 3-6 s        |
| Pattern detection + aggregation (CPU)                 | 3 s      | 2-5 s         | 2-5 s               | 2-5 s        | 2-5 s        |
| LLM coaching notes (DeepSeek 14B Q4_K_M, ~600 tokens) | 18 s     | n/a           | 14-22 s @ ~35 tok/s | 12-20 s      | 4-8 s        |
| PDF render                                            | 3 s      | 2-4 s         | 2-4 s               | 2-4 s        | 2-4 s        |
| **Total p50**                                         | **82 s** | **100-160 s** | **65-110 s**        | **62-105 s** | **30-60 s**  |

**Verdict:** 90s p50 holds on A10G or L4 with the 14B LLM. T4 is **not viable** as a primary worker — it can serve as a degraded-mode fallback only.

### 8.3 LLM choice

- **Primary:** DeepSeek V4 14B Q4_K_M, served via Ollama on A10G. ~14-22s for ~600 output tokens at ~35 tok/s.
- **NOT viable:** DeepSeek V4 32B on A10G. ~50s+ per inference; breaks the p95 budget alone.
- **H100 fallback for 32B:** cost-prohibitive at 1k DAU; reconsider at 10k DAU if quality regressions surface.
- **Hosted LLM fallback feature flag:** Anthropic Claude Haiku and Together (Llama 3.1 70B) — enabled via Statsig flag for capacity surge events (federation finals, viral moment). The flag is in place from Sprint 11; the integration is built and tested even if normally disabled. Cost-control: only the coaching-notes prompt is hosted, never the per-shot diagnostic ensemble.

---

## 9. Backend SLAs

| Endpoint class                                             | p50    | p95        | p99          |
| ---------------------------------------------------------- | ------ | ---------- | ------------ |
| API reads (sessions, shots, athletes, leaderboards)        | 40 ms  | 120 ms     | **≤ 200 ms** |
| API writes (annotation, settings, comment)                 | 80 ms  | 250 ms     | **≤ 500 ms** |
| Authenticated session bootstrap (login → first feed event) | 600 ms | 1.4 s      | 2.0 s        |
| LLM coaching-note endpoint (synchronous slow path)         | 12 s   | **≤ 25 s** | 35 s         |
| Webhook delivery (federation tier)                         | 800 ms | **≤ 5 s**  | 8 s          |
| Mobile sync (offline replay on reconnect)                  | 2 s    | 8 s        | 15 s         |

**Why p99 not p95 for read/write:** at 1k DAU producing ~200 shots/session × ~100 concurrent live sessions on a Saturday morning, p99 is hit by a real user every few seconds. p95 is too lax.

---

## 10. Network resilience

### 10.1 Wi-Fi link to Hero 13

- **Drop window tolerated without UI degradation:** ≤ 2s. The session continues; the "Live feed delayed" banner does not appear.
- **Reconnect window:** ≤ 5s. Beyond 5s of disconnection, surface "Reconnecting to camera…" banner. The recording continues on the camera regardless — **we never lose recording** because we never depended on the link to record. Hero 13 records to its own SD card; we ingest the recorded MP4 post-session if Wi-Fi was lossy.
- **BLE keepalive during Wi-Fi outage:** the BLE link stays up; we use it to verify the camera is still recording. If BLE also drops, we surface "Camera link lost — verify recording on camera" and continue the audio-only pipeline on the operator phone's mic as a degraded fallback.
- **2.4 GHz fallback prohibited** in our config. Force 5GHz per `05-embedded-firmware-engineer.md` Section "Outdoor Failure Modes." Accept the ~10m range hit; mount the phone closer or USB-C tether the operator station.

### 10.2 Mobile to backend

- **Offline session capture: full parity.** The mobile app records, detects shots, runs diagnostics, and renders the live feed entirely offline. No backend round-trip is on the live coaching path.
- **Sync within 10s of reconnect.** WatermelonDB sync log replays via tus.io chunked upload (5MB chunks, resumable). A 30-minute session with ~80 shots and ~1.5 GB of video syncs in 10s of session metadata + background upload of the video over the next several minutes.
- **Background upload constraint-aware:** WorkManager (Android) defaults to unmetered + charging; URLSession background config + `BGProcessingTaskRequest` (iOS). User-overridable for federation events where the operator phone is on a tethered hotspot.

---

## 11. Storage costs

### 11.1 The S3 egress cliff

S3 egress is the cost cliff for video-heavy workloads. At 1k DAU × 1 session/week × 1.5 GB/session × $0.09/GB egress = $585/month if every session is fetched once. At 10k DAU it's $5,850/month — and that's _if_ sessions are fetched once.

### 11.2 Required architecture

- **CloudFront signed URLs for direct mobile↔S3 transfers.** Mobile uploads via tus.io go to S3 directly; downloads (athlete reviewing their own session) go via CloudFront signed URLs. **Never proxy video through the API.**
- **CloudFront edge caches** in the regions where users live: us-east-1, eu-west-1, me-south-1 (Bahrain, for Egypt low-latency).
- **Tiered storage:** S3 Standard for the first 30 days; S3 Standard-IA after 30 days; S3 Glacier Instant Retrieval after 180 days. Federation tier opts out of Glacier (always Standard for instant pull during competitions).
- **Per-shot clip extraction post-session:** the full 30-minute video stays cold; per-shot 8-second clips (for the feed UI) are pre-extracted and cached hot. Reduces egress 95% for the typical "scroll through my shots" UX.

### 11.3 Cost-per-session target

**≤ $0.10 per session all-in** (storage + GPU + egress + LLM). At 1k DAU × 1 session/week × 4.3 weeks/month = ~$430/month variable cost. This is the budget the engineering team is held to — every architectural decision rolls up here.

---

## 12. Capacity planning at launch

### 12.1 DAU targets

- **Sprint 19 (Egypt validation):** 50 active testers
- **Launch:** 1k DAU
- **6 months post-launch:** 10k DAU
- **18 months post-launch:** 50k DAU (federation tier expansion)

### 12.2 Concurrent live session peak

The peak is **Saturday morning club hours**, 09:00-12:00 in US/EU/ME timezones rotating across the day. At 1k DAU with ~30% weekend activation, ~300 sessions across 3-4 peak hours = ~100 concurrent live sessions at peak. At 10k DAU, ~1000 concurrent.

### 12.3 GPU worker pool sizing

- **Ollama queue depth target:** ≤ 10 jobs. Beyond 10, p95 LLM latency breaches 25s SLA.
- **A10G workers at 1k DAU:** 4 workers. Each handles ~25 concurrent sessions over a 30-minute session window with the 90s post-session pipeline. Headroom: handles 2× peak.
- **A10G workers at 10k DAU:** 24 workers, autoscaled across 12-32 based on queue depth.
- **Autoscale signal:** Ollama queue depth (predictive) + GPU utilization (lagging). Scale up at queue ≥ 6, scale down at queue ≤ 2 sustained 5 minutes.
- **Cold-start budget:** ≤ 90s per worker (model load + warmup). Pre-warm 1 spare worker at all times during peak.

### 12.4 Database sizing

- **Postgres primary at 1k DAU:** db.r6g.xlarge (4 vCPU, 32 GB RAM). Read replicas: 2.
- **At 10k DAU:** db.r6g.4xlarge primary; 4 read replicas; sessions table partitioned by month.
- **TimescaleDB hypertable** for the time-series shot data. Retention: full-resolution 90 days, downsampled 1-year, aggregates forever.

---

## 13. Performance regression CI gates

### 13.1 Synthetic load rig

A phone on a tripod, in a thermal chamber at 35°C, replays a fixture session nightly in CI. The fixture session is a real Egypt session captured in Sprint 8 (or earlier dogfood) and checked in as a Git LFS blob (per `05-embedded-firmware-engineer.md` Section "Mock/Fixture Improvements").

The rig asserts:

- p95 shot-to-feed-entry latency ≤ 4s (Wi-Fi path)
- p95 glass-to-glass preview ≤ 1.8s (Wi-Fi path)
- Battery drain over the 30-minute fixture ≤ 9% (iPhone 13 baseline)
- Phone package temperature stays below 42°C (thermal chamber at 35°C ambient)
- Audio chunks dropped = 0
- Pose frames dropped < 5% of total

### 13.2 Merge gate

A regression on any of these assertions blocks merge. The CI job also publishes a histogram delta to the PR comment so the reviewer sees "this PR moved p95 pose latency from 38ms to 51ms" _before_ approving.

### 13.3 Backend perf gate

A k6 load script runs against the staging backend on every PR that touches API code. Asserts the p99 read/write SLAs from Section 9. Regression blocks merge.

---

## 14. What is deliberately NOT optimized for v1

The following devices and configurations are **out of scope** for V1 and ship as P1 work in Sprint 9:

- **Below iPhone 12 (A14 Bionic):** Older ANE, slower memory bandwidth, marginal on the pose+YOLO path. Lite-variant work.
- **Below Pixel 6a (Tensor G1):** Pixel 5 and earlier use Snapdragon 765/865 — viable but require the QNN delegate path which is Sprint 10 work.
- **Below Galaxy A54 (Exynos 1380):** A53 and earlier are below the supported floor.
- **iPad / tablets:** v1 is phone-only. Tablet support adds layout work and a different camera-mounting story; defer to v1.5.
- **Wear OS / Apple Watch companion:** "Tap to mark a hilight" use case; defer to v2.
- **Multi-camera live preview:** v1 supports multi-camera _recording_ (Sprint 17) and multi-camera _post-session_ analysis. Multi-camera _live_ preview (3-up grid) is v1.5.
- **4K live preview:** 2.7K30 only for live. 4K is recorded to SD card and analyzed post-session.
- **Live LLM coaching notes:** Coaching notes are _post-session only_ in v1. "Live coach voice" (sub-second LLM hint per shot) is v2 — depends on a custom small model, not DeepSeek 14B.

The Sprint 9 [P0] lite-variant work (per `04-mobile-app-builder.md` Sprint resequencing) ships INT8-quantized RTMPose and YOLO variants for the floor devices. Until then, the supported device list is enforced by a hard check on app launch.

---

## Appendix A: Source SLAs in one place

| SLA                                   | Target                           |
| ------------------------------------- | -------------------------------- |
| Shot-to-feed-entry, Wi-Fi p50         | 2.5s                             |
| Shot-to-feed-entry, Wi-Fi p95         | 4s                               |
| Shot-to-feed-entry, USB-C p50         | 1.2s                             |
| Shot-to-feed-entry, USB-C p95         | 2.0s                             |
| "Shot detected" (audio path) p95      | 800 ms                           |
| Visual diagnostic back-fill p95       | 2 s                              |
| Glass-to-glass preview, Wi-Fi p95     | 1.8s                             |
| Glass-to-glass preview, USB-C p95     | 600 ms                           |
| Battery drain iPhone 13 / Pixel 6a    | < 18% / < 22% per hour           |
| Phone thermal package temp            | < 42°C at 35°C ambient           |
| Post-session pipeline p50 / p95 / cap | 90s / 150s / 180s                |
| API read p99                          | 200 ms                           |
| API write p99                         | 500 ms                           |
| LLM endpoint p95                      | 25 s                             |
| Webhook delivery p95                  | 5 s                              |
| Wi-Fi reconnect window                | ≤ 5 s                            |
| Cost per session                      | ≤ $0.10                          |
| Live feed availability                | ≥ 99.5% during sessions          |
| Post-session pipeline success rate    | ≥ 99% (excluding user-cancelled) |
| Backend API availability              | ≥ 99.9%                          |

---

**Document status:** Canonical. Any change to a target in this document requires a written ADR explaining the rationale, the cost/benefit, and the architectural impact. Performance Benchmarker review required for sign-off.
