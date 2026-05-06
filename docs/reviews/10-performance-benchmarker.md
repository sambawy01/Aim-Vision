# AIMVISION V1 — Performance Posture Critique

**Reviewer:** Performance Benchmarker · **Date:** 2026-05-06 · **Source:** `AIMVISION_V1_Sprint_Build_Plan.txt` v1.0

## Live Latency Budget Table (end-to-end, p50, Wi-Fi path)

| Stage | Best case | Realistic | Notes |
|---|---|---|---|
| Hero 13 sensor → encoder → Wi-Fi preview emit | 250 ms | 400-600 ms | Hero 11/12 measured 800-1500 ms; Hero 13 unverified, assume similar floor |
| Wi-Fi 5GHz radio + UDP/RTP buffer to phone | 50 ms | 150-300 ms | Outdoor metal-rifle environment degrades to 2.4GHz fallback |
| H.264 hardware decode (VideoToolbox/MediaCodec) | 16 ms | 30-50 ms | One-frame queue typical |
| Frame copy → Rust core → tensor prep | 10 ms | 20-40 ms | UniFFI/JNI marshaling, color convert |
| Audio shot detection (per chunk, runs continuously) | 15 ms | 30-50 ms | Independent path; gate on this for "shot fired" |
| Pose inference (MediaPipe BlazePose Lite, NPU) | 20 ms | 30-60 ms | Subsample to 8-12 fps |
| YOLO barrel (YOLOv8n int8 quantized) | 25 ms | 40-80 ms | Subsample to 5-8 fps |
| Diagnostic classifier (post-shot, MLP over features) | 20 ms | 30-50 ms | Triggered only on shot event |
| Aggregation → JS bridge → React render | 30 ms | 80-150 ms | RN bridge is the silent killer |
| **Shot-to-feed-entry total** | **~700 ms** | **1.4-2.2 s** | Audio path |
| **Glass-to-glass preview + overlay** | **~400 ms** | **800-1100 ms** | Independent of shot pipeline |

## Critical Performance Risk: Live Feed Under 3s — Verdict

**The 1-second floor is unachievable on Wi-Fi.** GoPro Hero 11/12 wireless preview latency is documented at 1.0-1.5s on a good day, 2-3s with interference; Hero 13 has not been independently benchmarked and the plan assumes parity without evidence. Add audio detection + classifier + RN render and the realistic p50 is **1.8-2.5s, p95 likely 3-4s** — already breaching the 3s ceiling.

**Recommendations:**
1. Make USB-C tethered preview (Sprint 7 EPIC 7.2, currently P1) **P0 for federation tier** — it's the only credible path to <1s. Wired = 100-200ms glass-to-glass.
2. Reframe the budget honestly: **p50 ≤ 2.5s, p95 ≤ 4s on Wi-Fi; p50 ≤ 1.2s on USB-C**. The current "1-3s" is one number masquerading as a SLA.
3. Audio shot detection should fire the feed entry **before** visual diagnostic completes — show "Shot detected" within 800ms, then back-fill the diagnostic line within 2s. This decouples perceived from actual latency.

## On-Device ML Budget Recommendations

| Model | Target latency | Rate | Device baseline (p95) |
|---|---|---|---|
| Audio shot detector (CRNN/YAMNet-tiny) | 30 ms | every 20ms hop | iPhone 13: 25ms; Pixel 6a: 45ms; Galaxy S22: 30ms |
| MediaPipe Pose Lite (BlazePose) | 40 ms | 10 fps (subsampled from 24) | iPhone 13 ANE: 18ms; Pixel 6a NNAPI: 55ms |
| YOLOv8n int8 (barrel) — recommend over NAS/RTMDet for tooling maturity | 60 ms | 6 fps | iPhone 13: 35ms; Pixel 6a: 90ms |
| Diagnostic classifier (MLP over 30 engineered features) | 20 ms | per-shot only | All devices: <25ms |

**Audio chunk size:** 50ms hop with 200ms window. 10ms is overkill (latency win negligible vs CPU cost); 100ms loses sub-shot temporal resolution for double-shot disambiguation. **Backpressure:** drop pose first, then YOLO, never drop audio or preview decode. Implement a single mpsc channel with `try_send` and a per-stage drop counter exposed as a metric.

## Battery + Thermal Targets to Set Now (Don't Wait Until Sprint 19)

**Battery target: <18%/hour iPhone 13, <22%/hour Pixel 6a** during live session with preview + pose overlay, screen at 50% brightness. Required:
- Hardware H.264 decode (VideoToolbox/MediaCodec) — software decode would burn 35%+/hr
- ML on Apple Neural Engine / Android NNAPI/QNN (Hexagon) — CPU inference is non-viable
- Wi-Fi PSM disabled during session (low-latency mode), re-enabled between
- Skia/Metal GPU overlay rendering, never CPU canvas
- Background mode: pause inference, keep audio detector + recording link only

**Thermal target: sustained 60-min session at 35°C ambient (Egypt baseline) without throttling.** Phone CPU/GPU package <42°C. Graceful degradation ladder:
1. 42°C → drop pose to 5fps
2. 44°C → drop YOLO entirely, keep audio + preview
3. 46°C → drop preview to 12fps, keep audio + recording
4. 48°C → audio-only mode, surface "thermal protection active" banner

Hero 13 has its own thermal envelope — budget **3 minutes of cooldown per 20 minutes of 4K capture** in 35°C+. Test plan must include a 90-minute outdoor session at solar noon, not a lab simulation.

## Post-Session 90s Feasibility Check (30-min session, backend GPU)

| Stage | Budget | Reality on T4/A10G |
|---|---|---|
| Video re-fetch from object storage (4GB @ 1Gbps) | 8s | 10-15s on T4 region; 5s with CloudFront edge |
| Re-decode + frame extraction (every 6th frame, 30min) | 12s | 8-15s with NVDEC |
| Full-res pose (HRNet-W32 @ ~10 fps GPU) | 25s | 20-30s on A10G; 50s+ on T4 |
| Audio re-detection (Whisper-tiny + custom) | 5s | 3-8s |
| Per-shot diagnostic ensemble (~80 shots) | 8s | 6-12s |
| Pattern detection + aggregation | 3s | 2-5s |
| **DeepSeek V4 coaching notes (recommend 14B Q4_K_M, ~600 output tokens)** | **18s** | **A10G: 14-22s @ ~35 tok/s; 32B is 50s+ — too slow** |
| PDF render | 3s | 2-4s |
| **Total p50** | **82s** | **65-110s** |

**Verdict: 90s p50 holds on A10G with 14B LLM; p95 will breach to 130s.** Recommend stating budget as **p50 ≤ 90s, p95 ≤ 150s, hard cap 180s with degraded report fallback.** 32B DeepSeek is not viable on a single A10G — go 14B or run 32B on H100 (cost prohibitive). T4 is too slow for HRNet at full-res; budget A10G or L4 minimum.

## Instrumentation Plan — 5 Specifics (Pull Forward from Sprint 22)

1. **OpenTelemetry from Sprint 6**, not 22. Span per ML stage on-device (audio_detect, pose_infer, yolo_infer, classifier, render), exported via OTLP/HTTP batched every 30s. Without this, "1-3s feed latency" is unverifiable.
2. **Per-stage histogram metrics** (p50/p95/p99) for: wifi_preview_lag, decode_lag, pose_lag, classifier_lag, bridge_lag, shot_to_feed_lag. Surface as a debug overlay toggleable in dev builds from Sprint 7.
3. **Firebase Performance Monitoring + Sentry Performance** on mobile from Sprint 5; Datadog APM on backend from Sprint 6. RUM on the live session screen specifically — that's the screen that will fail in production.
4. **Synthetic load rig**: a phone-on-a-tripod replaying recorded fixture sessions nightly in CI, asserting p95 latency budgets. Catches regressions before Egypt does. Should exist by Sprint 8.
5. **Battery + thermal telemetry from Sprint 7**: sample `UIDevice.batteryLevel` and `ProcessInfo.thermalState` (iOS) / `BatteryManager` + `PowerManager.currentThermalStatus` (Android) every 10s during live sessions, ship to backend. Build the dataset now so Sprint 19's "measure" task is "analyze 6 months of real data," not "start measuring."

---

**Performance Status:** FAILS as written. The 1-3s live feed SLA is not credibly achievable on Wi-Fi at p95. The 90s post-session budget is achievable but tight, with no headroom and undefined p95. Battery/thermal deferral to Sprint 19 is the single biggest performance risk in the plan — by then the architecture is locked.

**Scalability Assessment:** Needs Work. Backend ML worker pool, Ollama queueing, p95 budgets, and APM are all absent from the plan and must be designed in by Sprint 11, not Sprint 22.
