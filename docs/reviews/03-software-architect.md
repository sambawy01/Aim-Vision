# AIMVISION V1 — Architecture Critique

**Reviewer:** Software Architect · **Date:** 2026-05-06 · **Source:** `AIMVISION_V1_Sprint_Build_Plan.txt` v1.0

## Top 3 Questionable Decisions

**1. Rust core via UniFFI + JNI under React Native.** The stated win — one camera-protocol implementation — is real but narrow. Open GoPro is BLE pairing, an HTTP/1.1 client, MP4 file pulls, and a UDP/RTP preview tap. That's ~3-5k lines of unglamorous protocol code, not a CV kernel. Wrapping it in Rust means: cbindgen/UniFFI per release, two FFI surfaces to debug (Swift+UniFFI, Kotlin+JNI), async cancellation across three runtimes (Tokio, GCD, Kotlin coroutines), and a hiring pool of maybe 200 people globally who can do all three. **This pays off only if** (a) the camera protocol logic exceeds ~5k lines and changes often, (b) you run the same core on a desktop/edge/Linux federation appliance, or (c) DSP/CV code lands in the same crate. **It does not pay off** for a protocol shim alone — TypeScript with `react-native-ble-plx` + `fetch` plus a thin Swift/Kotlin USB-C module would ship faster. KMM is a worse trade than either: same interop tax, weaker async story, no desktop story. The honest framing: this is an investment in V2 (custom hardware, on-prem appliance), not V1 leverage. If V2 is uncertain, defer.

**2. Backend "Node.js or Python TBD."** The ML training, ONNX preprocessing, Ollama integration, and post-session pipeline are all Python. Splitting languages means you reimplement DTOs, run two CI toolchains, and fragment SREs. **Recommendation: FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Arq/RQ for queues, with Uvicorn behind Granian.** You get async I/O parity with Node, type safety via Pydantic, and zero impedance with the ML stack. The only reason to pick Node is if the team is Node-native — and the plan reads ML-heavy.

**3. Single Postgres on Railway as the only persistence story.** Railway is fine through Sprint 18. Federation on-prem is a different beast. **Bridge: CloudNativePG operator** (Crunchy is the alternative; Zalando is older). Same Postgres binary, declarative HA, runs on Railway-managed today and a federation k3s appliance tomorrow. Pair with **Litestream→S3** for cloud DR and pgBackRest for on-prem. Avoid Docker-compose-only for federation — clubs can't operate it.

## Missing Concerns (7)

- **Event sourcing for shot events.** EPIC 8.2's "local event store + sync" is implicitly an append-only log. Make it explicit: shot events as immutable facts with `(session_id, monotonic_seq, device_clock, server_clock)`, CRDT-friendly, no edits. This kills 80% of the "conflict resolution" work in EPIC 12.1. See Fowler's *Event Sourcing* and the offline-first work in Riffle/ElectricSQL.
- **Long-running job orchestration.** The 90-second post-session pipeline needs retries, idempotency, and visibility. **Use Temporal** (or Inngest if you want serverless). A "plain queue + worker" rebuilds Temporal badly by Sprint 14.
- **Live frame streaming through the RN bridge.** This is the silent killer. JS bridge throughput on RN's old architecture chokes at ~10 MB/s of marshaled data; 1080p30 H.264 decoded to RGBA is ~180 MB/s. **Do not push frames through the bridge.** Decode natively, render to a `SurfaceView`/`MTKView`, expose only handles. For pose overlay, run ONNX in the native module and emit *keypoints* (a few KB/frame) over the bridge. Adopt RN's New Architecture (Fabric + JSI) from day one — TurboModules + JSI lets you share frame buffers without serialization.
- **Multi-tenancy model.** Solo/Club/Federation isolation isn't specified. **Recommendation:** row-level tenancy (`organization_id` everywhere + Postgres RLS) for cloud Solo/Club; **separate database per federation on-prem** for sovereignty/GDPR/data-residency. Schema-per-tenant is the worst of both — migration hell at scale.
- **ML model versioning + shadow eval.** No mention of model registry, shadow routing, or rollback. **MLflow Model Registry** + a `model_version` column on every prediction; route 5% to candidate model, compare against Franco's labels in a feedback loop.
- **Time-series for longitudinal analytics.** EPIC 14 will outgrow Postgres aggregates fast. **TimescaleDB extension** (no infra change) covers V1; **ClickHouse** for federation cohort analytics in V2.
- **QR check-in token design.** JWT with short-lived (30s) `exp`, `aud=club:<id>`, `scope=checkin`, single-use jti tracked server-side. **PASETO v4.local** is better than JWT here (no algorithm confusion, smaller). OAuth device-code is overkill.

## Scaling Cliffs (3)

1. **RN bridge at 30fps frame data** (Sprint 7) — addressed above; non-negotiable redesign.
2. **S3 egress on cloud video** — full-resolution session video round-tripping S3→backend→mobile will dominate cost by Sprint 19. Mitigation: **CloudFront signed URLs** for direct mobile→S3 writes and reads; never proxy video through the API.
3. **Ollama single-instance for LLM** (Sprint 11) at launch volume — if 1k DAU each generate one report, that's 1k LLM calls/day at ~10s each = serial bottleneck. **Run Ollama behind a queue with 3-4 GPU workers, or fall back to hosted (Anthropic/Together) with a feature flag.** The plan's R12 hints at this; make it architectural, not contingent.

## Build vs Buy (5)

- **Auth:** don't build. Use **Clerk** or **WorkOS** (Apple/Google/email/SAML for federations).
- **Payments:** don't build. **Stripe** + **RevenueCat** for iOS/Android IAP unification.
- **Video CDN:** **Mux** or **Cloudflare Stream** — adaptive bitrate, signed URLs, thumbnails, all built.
- **Observability:** **Sentry** (errors) + **Grafana Cloud** or **Axiom** (logs/metrics/traces). Don't roll your own.
- **Feature flags + experiments:** **Statsig** or **PostHog** — critical for ML A/B routing and tier gating.

Already correctly buying: CVAT (annotation), ONNX Runtime, Postgres. Already correctly building: camera core (justified if V2 hardware lands), ML models (your moat).

## 3 High-Leverage Redesigns

**1. Frame pipeline as native-only with JSI keypoint bridge.** Decode H.264 natively (AVFoundation / MediaCodec) → render to native surface → run ONNX pose in the native module on a YUV tensor → emit keypoint structs over JSI (not the old bridge). Pose overlay is a `<Skia>` canvas in RN reading keypoints at 30Hz. This eliminates the Sprint 7 frame-rate risk entirely and is the single change with the highest "won't-have-to-rewrite-in-Sprint-19" value.

**2. Event-sourced shot log + CQRS reports.** Shots are append-only events; live feed reads from the event stream; post-session report is a projection rebuilt by the Temporal pipeline. Sync becomes "stream new events with monotonic seq since last cursor" — no merge conflicts, replayable, audit-ready, and the longitudinal pipeline (Sprint 14) becomes a second projection over the same log. Reference: Greg Young's CQRS, and the architecture of Linear's sync engine.

**3. Cloud↔on-prem parity via CloudNativePG + a single Helm chart.** One k3s-deployable bundle (API, workers, Postgres, MinIO, Ollama) that runs identically on Railway-managed-k8s and a federation appliance. This kills the "rewrite for on-prem in Sprint 17" cliff before it forms, and makes Sprint 17's EPIC 17.5 a one-day validation instead of a sprint.
