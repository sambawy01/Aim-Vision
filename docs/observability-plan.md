# AIMVISION Observability Plan

**Owner:** Performance Benchmarker
**Status:** Canonical (supersedes the Sprint 22 "instrumentation" stub in `AIMVISION_V1_Sprint_Build_Plan.txt` v1.0)
**Last reviewed:** 2026-05-06
**Cited reviews:** `docs/reviews/04-mobile-app-builder.md`, `docs/reviews/05-embedded-firmware-engineer.md`, `docs/reviews/10-performance-benchmarker.md`
**Companion document:** `docs/performance-budgets.md`

---

## 1. From Sprint 3, not Sprint 22

The V1 plan defers observability infrastructure (Sentry, OTel, RUM, APM) to Sprint 22 — three sprints after the Egypt validation sprint. This is backwards. **Egypt validation is unobservable without telemetry.** When the federation tester says "the feed felt slow on Saturday morning," the plan as written gives the team nothing to look at — no traces, no histograms, no crash reports, no battery curves. They have to fly back to Cairo to repro.

Sentry, OTel, Firebase Performance, and Statsig feature flags are **infrastructure, not polish**. They land in Sprint 3-4 alongside the foundational mobile architecture. The Sprint 22 entry in the V1 plan is replaced by "harden dashboards and runbooks" — the _plumbing_ exists from Sprint 3.

This is a direct echo of `04-mobile-app-builder.md` ("Sentry/Crashlytics from Sprint 3, not Sprint 22") and `10-performance-benchmarker.md` ("OpenTelemetry from Sprint 6, not 22 ... Battery + thermal telemetry from Sprint 7").

---

## 2. Stack

### 2.1 Errors: Sentry

- **React Native JS:** `@sentry/react-native` with Hermes source-maps and native stack traces.
- **iOS native (Swift / Obj-C):** `sentry-cocoa` linked into the host app for native crashes outside the JS layer.
- **Android native (Kotlin / JNI):** `sentry-android` + NDK plugin for native crash reports.
- **Rust core:** `sentry-rust` panic hook installed at core init. Captures Rust panics with full backtraces; cross-references the mobile error.
- **Backend (FastAPI):** `sentry-sdk[fastapi]` middleware with request-context tagging.
- **Temporal workers:** `sentry-sdk` initialized per worker with workflow-id and activity-name tags.

Single Sentry org, environments split as `mobile-prod`, `mobile-staging`, `backend-prod`, `backend-staging`, `egypt-validation`. Per-release deploy markers tied to the EAS Update channel and the backend Git SHA.

### 2.2 Logs / Metrics / Traces: Grafana Cloud

**Recommendation: Grafana Cloud over Axiom or Datadog.**

- OTel-native — no proprietary agent for the mobile app to ship.
- One vendor for logs (Loki), metrics (Mimir / Prometheus), traces (Tempo), and dashboards. Datadog is the alternative but at our DAU it is 3× the cost for marginal additional features.
- Free tier covers staging; the paid tier kicks in at production scale.

Axiom was considered. It is excellent for log volume cost, but its tracing story is weaker than Tempo and we want unified trace/metric/log correlation in a single pane.

### 2.3 Mobile RUM

- **Firebase Performance Monitoring** for the standard mobile RUM signals (app start, screen load, network requests). Free at our scale, well-understood by RN.
- **Sentry Performance** for the custom transaction spans (live session, shot detection, post-session pipeline). Same vendor as crash reporting; trace context links across.

These are complementary, not competing — Firebase is the broad RUM signal, Sentry is the targeted transaction tracing.

### 2.4 Synthetic monitoring

- **Phone-on-tripod synthetic load rig** in a thermal chamber, nightly CI (per `performance-budgets.md` Section 13). Replays a fixture Egypt session and asserts p95 latency, battery, thermal targets.
- **UptimeRobot** for backend HTTP endpoint liveness — every 60s on `/health`, `/api/v1/sessions/healthcheck`, `/api/v1/llm/healthcheck` from us-east-1, eu-west-1, me-south-1.
- **Pingdom alternative considered but UptimeRobot's free/cheap tier is sufficient at v1.**

### 2.5 APM: Grafana APM

Same vendor consolidation argument as Section 2.2. Grafana APM (Tempo + Mimir + Loki + Faro for browser RUM) covers the backend APM story. The PWA fallback (Sprint 1, per `04-mobile-app-builder.md`) gets Grafana Faro RUM.

Datadog is the alternative. Picked Grafana for cost and OTel-nativeness. Re-evaluate at 10k DAU.

---

## 3. OpenTelemetry instrumentation from Sprint 3

### 3.1 Mobile spans (on-device)

A span per ML stage, exported via OTLP/HTTP batched every 30 seconds (battery cost minimal):

- `audio_detect` — per-chunk audio shot detection
- `pose_infer` — per-frame pose inference (sampled to 10% of frames to bound metric cardinality)
- `yolo_infer` — per-frame YOLO barrel inference (sampled to 10%)
- `classifier` — per-shot diagnostic MLP
- `render` — per-frame Skia composite + Fabric commit
- `shot_to_feed` — root span from shot-detected event to feed-entry rendered
- `live_session` — root span for the entire session, child spans for everything above
- `wifi_reconnect` — every Wi-Fi link drop/reconnect cycle, with `drop_duration_ms` and `reconnect_duration_ms` attributes
- `ble_pair`, `ble_disconnect` — BLE link lifecycle events

### 3.2 Backend spans

Auto-instrumented via OTel:

- HTTP request span (FastAPI middleware) — includes route, status, duration
- Database query span (SQLAlchemy / asyncpg instrumentation) — includes query plan hash (NOT the query itself, to keep PII out)
- Temporal activity span — wraps each activity invocation
- S3 transfer span — upload/download size, region, duration
- Ollama inference span — model name, input token count, output token count, queue wait time, inference duration

### 3.3 Trace context propagation

A single trace ID flows from mobile → backend → Temporal worker → Ollama:

- Mobile → backend: `traceparent` HTTP header injected by the OTel SDK on every API call.
- Backend → Temporal: trace context serialized into the workflow input payload, deserialized at activity entry.
- Temporal → Ollama: the activity span is the parent of the Ollama span.

The result: a single trace shows "user tapped 'analyze session' → 102s end-to-end → broken down by stage." When p95 breaches 150s, we open one trace and see which stage exploded.

### 3.4 Resource attributes

Every span carries:

- `app_version` (e.g., `1.4.2`)
- `device_model` (e.g., `iPhone14,2`)
- `os_version` (e.g., `iOS 17.4.1`)
- `ml_model_versions` (e.g., `pose=rtmpose-lite-v3,yolo=v8n-int8-v2,audio=crnn-v4`)
- `network_type` (`wifi`, `cellular`, `usb`, `offline`)
- `athlete_tenant_hash` — **NEVER `athlete_id` raw.** A stable per-tenant SHA256 hash with a per-environment salt. We can correlate "all events from one athlete" within an environment without ever shipping the PK.

This list is non-negotiable. Anything dropped from it makes the dashboards in Section 12 ineffective.

---

## 4. Histograms required (p50/p95/p99)

The following histograms are the spine of every performance dashboard. They must exist by Sprint 5:

- `wifi_preview_lag_ms` — Hero 13 emit to phone-decoded preview frame
- `decode_lag_ms` — H.264 hardware decode time per frame
- `pose_lag_ms` — pose inference per frame (sampled)
- `yolo_lag_ms` — YOLO inference per frame (sampled)
- `classifier_lag_ms` — per-shot diagnostic MLP time
- `bridge_lag_ms` — JSI HostObject call to Skia composite (the canary for any RN bridge regression)
- `shot_to_feed_lag_ms` — the user-facing SLA (Section 2.1 of `performance-budgets.md`)
- `audio_detect_lag_ms` — per-chunk audio detector latency (the 800ms SLA target)
- `post_session_pipeline_total_s` — full post-session pipeline duration
- `llm_inference_s` — Ollama inference time, dimensioned by model name
- `db_query_ms` — backend DB query duration, dimensioned by route
- `s3_egress_bytes_per_s` — upload/download throughput
- `sync_replay_time_s` — mobile sync log replay on reconnect

Histogram buckets are tuned per metric — exponential buckets for latency (1ms, 2ms, 4ms, ... 32s), linear for byte sizes, dedicated wide buckets for the LLM inference metric (5s, 10s, 15s, 20s, 25s, 30s, 45s, 60s, 90s, 120s).

---

## 5. In-app debug overlay

Toggleable in dev builds (and in prod via a long-press combo on the version label, gated behind a Statsig flag for staff users only) from Sprint 7.

The overlay surfaces all live histograms over the current frame in a corner of the live session screen. Each metric is rendered as:

- Current value (last 1s)
- p50 / p95 over the rolling 60s
- Color-coded against the budget in `performance-budgets.md`:
  - Green: under p50 budget
  - Yellow: between p50 and p95 budget
  - Red: over p95 budget

A 30-second flame-chart strip across the bottom shows recent shot-to-feed-entry traces, so an engineer can see "this shot took 3.8s and the bottleneck was the bridge_lag." The overlay also shows the current `ProcessInfo.thermalState`, battery level, and Wi-Fi signal strength (RSSI dBm).

This is the single most important development tool the team builds. Every architecture decision from Sprint 7 onward gets evaluated against this overlay.

---

## 6. Synthetic load rig

Per `performance-budgets.md` Section 13. Lives in the CI pipeline by Sprint 8.

- Phone (iPhone 13 + Pixel 6a, two test rigs in parallel) on a tripod facing a high-refresh display playing back a recorded fixture session video at 24fps.
- A second display plays back synchronized audio of muzzle blasts (the audio path runs).
- BLE/Wi-Fi mock camera fixture from Sprint 5 (per `05-embedded-firmware-engineer.md` Section "Mock/Fixture Improvements") feeds GPMF telemetry as if from a real Hero 13.
- Thermal chamber set to 35°C ambient.
- Fault injection grammar: `t=12.3s drop_wifi for 4s`, `t=18s ble_disconnect`, `t=22s thermal_warn` — replayable nightly.
- Assertions: p95 shot-to-feed-entry ≤ 4s, audio_chunks_dropped = 0, battery drain ≤ 9% over 30min, phone package temp < 42°C, no crashes, no Sentry errors.
- A regression on any assertion blocks merge.

The rig also serves as the primary repro environment for any production incident: capture the production fixture (anonymized), feed it through the rig, observe the failure deterministically.

---

## 7. Battery and thermal telemetry

Sample every 10 seconds during a live session and ship via OTel batched export every 30 seconds.

### 7.1 iOS

- `UIDevice.current.batteryLevel` (-1 if monitoring disabled — enable on session start)
- `UIDevice.current.batteryState` (`.unplugged`, `.charging`, `.full`)
- `ProcessInfo.processInfo.thermalState` (`.nominal`, `.fair`, `.serious`, `.critical`)
- `ProcessInfo.processInfo.systemUptime` (anchor for clock skew detection)
- Optional: `os_proc_available_memory()` for memory pressure correlation

### 7.2 Android

- `BatteryManager.EXTRA_LEVEL` / `EXTRA_SCALE` for percentage
- `BatteryManager.EXTRA_STATUS` for charging state
- `PowerManager.currentThermalStatus` (`THERMAL_STATUS_NONE`, `LIGHT`, `MODERATE`, `SEVERE`, `CRITICAL`, `EMERGENCY`, `SHUTDOWN`)
- `Debug.MemoryInfo` for memory pressure

### 7.3 Backend telemetry table

Battery and thermal samples land in a TimescaleDB hypertable `device_telemetry`:

```
ts | tenant_hash | device_model | os_version | session_id | battery_pct | charging | thermal_state | memory_pressure | network_type | wifi_rssi
```

Dashboards in Section 12 query this table. The Sprint 19 Egypt validation report writes a query against this table — it is not a fresh measurement effort.

### 7.4 Build the dataset for Sprint 19 now

By Sprint 19, the team has 16 sprints of internal-dogfood battery/thermal data across iPhone 12/13/15/Pixel 6a/8/Galaxy A54/S22/S24. Sprint 19 _analyzes_ this data. The Sprint 19 deliverable is a written report comparing internal-dogfood baselines to Egypt session telemetry, surfacing the gap. That is a 1-week task instead of a 4-week task, because the data already exists.

---

## 8. Error budgets and SLOs

Aligned with `performance-budgets.md`:

### 8.1 SLOs

- **Live feed availability ≥ 99.5%** during sessions. "Available" means: shot-to-feed-entry latency < hard cap (6s Wi-Fi / 3s USB-C) AND no degraded-banner shown for > 60 cumulative seconds in the session.
- **Post-session pipeline success rate ≥ 99%** excluding user-cancelled jobs. "Success" means: report generated within 180s hard cap with no error status.
- **Backend API availability ≥ 99.9%** measured at the load balancer. Excludes scheduled maintenance windows announced ≥ 24h in advance.
- **Live audio shot-detection recall ≥ 95%** vs ground-truth. (This is an ML SLO, not a pure system SLO, but observable via the synthetic rig nightly.)

### 8.2 Error budgets

A 99.5% availability SLO over a 30-day window allows 3.6 hours of "down" time. The error budget is consumed continuously; when 50% is consumed, alert the team; when 100% is consumed, freeze non-critical deploys until the budget recovers.

### 8.3 Burn rate alerts

Wired to PagerDuty (Section 9):

- **2% of monthly budget burned in 1 hour** → P1 alert (something is wrong right now)
- **5% of monthly budget burned in 6 hours** → P1 alert (sustained issue)
- **10% of monthly budget burned in 3 days** → P2 alert (slow leak)

Burn rate is computed continuously by a Grafana Mimir recording rule.

---

## 9. Alerting

### 9.1 Routing

- **Sprint 3-9 (pre-SRE):** Sentry alerts and PagerDuty go to a shared `#oncall` Slack channel. The on-call engineer is whoever is awake and on the founders' rotation. Document this explicitly in the team agreement — no implicit ownership.
- **Sprint 10+ (SRE part-time):** PagerDuty rotation with primary + secondary. SRE owns the rotation; the founding engineers are escalation tier 2.

### 9.2 P1 alerts (page immediately, 24/7)

- Backend API availability < 99% over 5 minutes
- Backend API p99 latency > 2× budget over 5 minutes (read > 400ms, write > 1000ms)
- Ollama queue depth > 50 jobs sustained 3 minutes
- DB CPU > 90% sustained 5 minutes
- DB connection pool exhausted
- Sentry error rate spike (>10× the 7-day baseline) over 5 minutes
- Synthetic monitor (UptimeRobot) failure for ≥ 3 consecutive checks
- Cost-per-session metric > 2× budget over 1 hour (cost runaway protection)

### 9.3 P2 alerts (Slack ping during business hours)

- Sentry error rate > 1% of session count
- Single-tenant anomaly: one tenant generating > 10× the median tenant's error rate
- Feature flag drift (a flag intended to be 100% rollout is at < 95%, or vice versa)
- Disk usage > 80% on any worker
- Battery telemetry showing > 25%/hour drain on iPhone 13 across multiple sessions (architectural regression detector)
- Phone thermal telemetry showing `.critical` state > 5% of session time (thermal regression)

### 9.4 Auto-remediation hooks

For some P1 alerts, automated remediation runs _before_ the page:

- Ollama queue > 30 → autoscale spin up an extra A10G worker (the page only fires if the queue stays high after autoscale completes)
- Backend pod CPU > 90% → HPA already scales; the alert tracks if scale-up succeeded
- Wi-Fi reconnect spam from one tenant → no auto-remediation, but tag the tenant for support outreach

---

## 10. Privacy of telemetry

This section is non-negotiable.

### 10.1 Athlete identity

- **NEVER ship `athlete_id` raw** in any span attribute, log line, metric label, or dashboard.
- Tokenize as `athlete_tenant_hash = SHA256(athlete_id || tenant_salt)`. The salt is per-environment and rotates annually.
- The hash is stable enough to correlate "all events from one athlete" within an environment, but reverses to nothing without the salt.
- Internal lookup (support, debug) goes through a privileged API that takes an athlete_id and returns the hash, audited.

### 10.2 LLM prompts and responses

- LLM prompts and responses are **NEVER persisted to APM** (Sentry/Grafana). Treat them as PII-bearing by default.
- They land in a dedicated `llm_audit` table with field-level redaction (athlete name → tenant_hash, location → coarsened to country) before write.
- Retention 90 days unless flagged for federation review.

### 10.3 IP and User-Agent

- Hash IP at ingest (per-environment salt, reversible only via a privileged endpoint).
- User-Agent: parse to `device_model + os_version` and discard the raw string.

### 10.4 Video and audio

- Video and audio never flow through APM. Period. Never log a presigned URL with credentials in it.

### 10.5 Right to be forgotten

- A `DELETE /api/v1/athletes/{id}` request triggers a Temporal workflow that:
  - Deletes all S3 objects under that athlete prefix
  - Drops all DB rows
  - Replaces the tenant_hash in audit logs with `[DELETED]` (preserves audit timeline, removes correlation)
  - Confirms within 30 days per GDPR
- The deletion workflow itself is observable as a Temporal trace.

---

## 11. Cost discipline

Observability is famously expensive at scale. Defaults are set conservatively:

### 11.1 Trace sampling

- **Head sampling** on healthy traces at 1% (mobile) and 5% (backend). All errors and all traces with span duration > p95 budget are kept at 100%.
- **Tail sampling** on the backend via OTel Collector — keep all traces with `error=true`, `duration > p95`, or `status >= 500`.

### 11.2 Log volume

- INFO-level logs sampled at 10% in prod; DEBUG only in dev/staging.
- Structured JSON only — never log a stack-blob.
- Per-route log budget: > 100 log lines per request triggers an alert (a developer left a debug print in).

### 11.3 RUM event filtering

- Only ship Firebase Performance traces for screens we care about: `LiveSession`, `PostSessionReport`, `ShotFeed`, `Login`. Not every screen.

### 11.4 Sentry release-health gating

- Use Sentry release-health to gate EAS Updates: a release with crash-free-sessions < 99% triggers an automatic rollback prompt.
- This wires release health to deploy decisions, not just bug counts.

### 11.5 Cost alerts

A weekly cost-tracking dashboard panel (Section 12) and a P2 alert if the weekly Grafana Cloud + Sentry + Firebase bill exceeds the projected budget by > 20%.

---

## 12. Dashboards (must exist by Sprint 6)

Six dashboards in Grafana Cloud, each with a defined panel inventory:

### 12.1 Live Feed Latency

- Histogram heatmap: `shot_to_feed_lag_ms` over time, dimensioned by network_type
- p50 / p95 / p99 timeseries with budget overlays (the 2.5s / 4s / 6s lines drawn)
- Stacked bar: per-stage latency contribution (audio_detect + pose_infer + yolo_infer + classifier + bridge + render)
- Drop counters: `audio_chunks_dropped`, `pose_frames_dropped`, `yolo_frames_dropped`, `preview_frames_dropped`
- Wi-Fi reconnect rate per session
- Top 10 offending devices by p95 latency (helps spot a bad firmware combo)

### 12.2 Post-Session Pipeline Health

- Histogram heatmap: `post_session_pipeline_total_s` with budget lines (90s / 150s / 180s)
- Per-stage stacked bar (re-fetch + decode + pose + audio + classifier + LLM + PDF)
- Ollama queue depth timeseries
- LLM tok/s by model
- Worker pool utilization (A10G occupancy)
- Failure rate by stage (which stage tends to be the failure point)

### 12.3 Backend Reliability

- API request rate, error rate, p50/p95/p99 latency by route
- DB CPU, connection pool, query p99 by route
- Temporal workflow success/failure rate
- S3 throughput
- Webhook delivery success rate

### 12.4 Mobile Crash + ANR Trend

- Crash-free sessions percentage by app version (Sentry release health)
- ANR rate (Android-only) by device model
- JS exceptions vs native exceptions
- Top 10 crashes by event count
- Hermes vs JSC issues (sanity check no fallback-to-JSC happened in prod)

### 12.5 Tenant Isolation Audit

- Cross-tenant query attempts blocked (count over time)
- Tenant-scoped audit log search panel
- Top 10 tenants by storage, request count, error rate (each is also the "noisy neighbor" detector)
- Failed authorization events by tenant

This dashboard exists to satisfy the federation tier's SOC2 expectations and to detect attempted exploits.

### 12.6 Cost Tracking

- Daily Grafana Cloud + Sentry + Firebase + AWS bill
- S3 egress bytes (the cost cliff metric)
- LLM cost per session (Ollama compute time × A10G hourly cost / sessions per hour)
- Cost per session (the `≤ $0.10` SLA from `performance-budgets.md` Section 11)
- Worker pool utilization (idle workers = wasted spend)

---

## 13. Runbooks

Each P1 alert has a runbook stub at `docs/runbooks/<alert-name>.md`. Stubs ship in Sprint 6. They expand as we learn from incidents.

Initial set:

- `docs/runbooks/backend-down.md`
- `docs/runbooks/ollama-queue-saturated.md`
- `docs/runbooks/db-cpu-saturated.md`
- `docs/runbooks/api-latency-breach.md`
- `docs/runbooks/sentry-error-spike.md`
- `docs/runbooks/synthetic-monitor-failure.md`
- `docs/runbooks/cost-runaway.md`
- `docs/runbooks/wifi-reconnect-spam.md`
- `docs/runbooks/thermal-throttle-storm.md`

Each runbook has a fixed structure: symptom, blast radius, immediate mitigation, diagnostic queries (Grafana panel links pre-filtered), root-cause checklist, escalation path. The escalation path always ends at "wake the on-call founder."

---

## 14. Sprint resequencing — explicit

Per `04-mobile-app-builder.md` and `10-performance-benchmarker.md`, the V1 plan's Sprint 22 "instrumentation" line is replaced with the following sequencing:

| What                                                 | V1 plan placement    | Corrected placement                                                                               |
| ---------------------------------------------------- | -------------------- | ------------------------------------------------------------------------------------------------- |
| Sentry (RN, native, Rust, FastAPI)                   | Sprint 22            | **Sprint 3**                                                                                      |
| OpenTelemetry SDK + OTLP exporter                    | Sprint 22            | **Sprint 3**                                                                                      |
| Statsig (or PostHog / Unleash) feature flags         | Sprint 22            | **Sprint 3**                                                                                      |
| EAS Update (OTA)                                     | "later"              | **Sprint 4**                                                                                      |
| Firebase Performance Monitoring + Sentry Performance | Sprint 22            | **Sprint 5**                                                                                      |
| Histogram metric instrumentation (Section 4)         | Sprint 22            | **Sprint 5**                                                                                      |
| Battery + thermal telemetry                          | Sprint 19            | **Sprint 4**                                                                                      |
| In-app debug overlay                                 | not planned          | **Sprint 7**                                                                                      |
| Synthetic load rig                                   | not planned          | **Sprint 8**                                                                                      |
| PrivacyInfo.xcprivacy manifest                       | "later"              | **Sprint 4**                                                                                      |
| PagerDuty rotation                                   | not planned          | **Sprint 10**                                                                                     |
| Dashboards (Section 12)                              | not planned          | **Sprint 6**                                                                                      |
| Runbook stubs                                        | not planned          | **Sprint 6**                                                                                      |
| Tenant-isolation audit dashboard                     | not planned          | **Sprint 11**                                                                                     |
| Sprint 22 deliverable                                | "instrument the app" | **"harden dashboards, refine alert thresholds against real data, write incident-response retro"** |

The Sprint 22 work in V1 was misframed. The right Sprint 22 deliverable is _iteration on observability_, not the _introduction of observability_. By Sprint 22, every code path is traced, every screen is RUM'd, every alert has a runbook. Sprint 22 polishes that into a SOC2-grade observability posture.

---

**Document status:** Canonical. Any change to a vendor selection (Section 2) requires a written ADR and Performance Benchmarker review. Any change to the privacy posture (Section 10) requires legal sign-off in addition to engineering review.
