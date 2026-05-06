# AIMVISION — Architecture Overview

**Version:** 1.0 · **Date:** 2026-05-06 · **Owner:** Software Architect

This document is the master architectural reference for AIMVISION V1. It is the answer to "what does the system look like, and why?" Detailed designs live in linked Architecture Decision Records (ADR-0001 through ADR-0008) and in companion docs under `docs/security/`, `docs/compliance/`, and `docs/operations/`. When a section here disagrees with an ADR, the ADR wins.

---

## 1. Product context

AIMVISION is a coaching analytics platform for clay and skeet shooting sports built around a GoPro Hero 13–first capture stack, on-device computer vision, server-side multi-camera 3D reconstruction, and an LLM-authored coaching report. The product ships in three tiers — **Solo** (individual shooter, monthly subscription), **Club** (sporting-clays clubs and ranges, with a coach dashboard and roster management), and **Federation** (national governing bodies, with on-prem deployment, multi-camera triangulation, and talent-ID tooling). Our anchor design partner is the Egyptian Shooting Federation; Franco (former Olympic skeet coach) owns the diagnostic taxonomy. The competitive frame is documented in [Trend Researcher review](reviews/02-trend-researcher.md): we are not competing with MantisX (IMU-only) or ShotKam (passive video) but creating the analytics-and-coaching layer that no incumbent occupies. The defensible moat is the federation data flywheel plus multi-camera 3D ground truth — not the camera abstraction or the LLM wrapper.

The architecture must serve three deployment topologies (cloud-managed, hybrid, fully on-prem), three pricing tiers with materially different feature sets, and a hardware roadmap that may add custom AIMVISION-branded capture devices in V2. It must also degrade gracefully under desert-range conditions: 35–45 °C ambient, 2.4 GHz Wi-Fi congestion, intermittent connectivity, and operators who are coaches, not engineers ([Embedded review §Outdoor Failure Modes](reviews/05-embedded-firmware-engineer.md)).

---

## 2. System overview

The system is composed of seven runtime components and three trust boundaries. The diagram below shows the cloud-managed Solo/Club topology; the federation on-prem appliance replicates the same shape inside the federation's network with no outbound dependency on the cloud control plane (ADR-0005).

```
                              ┌──────────────────────────────────────────────┐
                              │         TRUST BOUNDARY: Public Internet      │
                              └──────────────────────────────────────────────┘

  ┌──────────────────┐    BLE / Wi-Fi AP / USB-C    ┌──────────────────────────────┐
  │  GoPro Hero 13   │◀─────────────────────────────▶│  aimvision-mobile (RN+JSI)   │
  │  (+ Insta360 X4  │   Open GoPro / UVC / GPMF    │  - Hermes / Fabric / Turbo   │
  │   in V2)         │                              │  - Skia overlay / Reanimated │
  └──────────────────┘                              │  - WatermelonDB (offline)    │
            ▲                                       │  - aimvision-camera-core (Rust)│
            │ shared C ABI for frame data            │     UniFFI control plane     │
            │                                       │     extern "C" media plane   │
            │                                       └──────────────┬───────────────┘
            │                                                      │ HTTPS + tus.io
            │                                                      │ + WebSocket (live)
            │                                                      ▼
            │                          ┌─────────────────────────────────────────────┐
            │                          │            Edge / CDN (Cloudflare)          │
            │                          │  - Cloudflare Stream (video)                │
            │                          │  - signed URLs (S3 direct upload/playback)  │
            │                          └────────────────┬────────────────────────────┘
            │                                           │
  ┌─────────┴────────┐                                  │
  │ aimvision-web    │  HTTPS                            │
  │ (React + TS)     │─────────────────────────────────▶ │
  │ Coach dashboard, │                                   │
  │ federation admin │                                   │
  └──────────────────┘                                   ▼
                              ┌──────────────────────────────────────────────┐
                              │   TRUST BOUNDARY: API gateway (mTLS, OIDC)   │
                              └──────────────────────────────────────────────┘
                                                        │
                       ┌────────────────────────────────┼────────────────────────────────┐
                       ▼                                ▼                                ▼
        ┌──────────────────────────┐    ┌──────────────────────────┐     ┌──────────────────────────┐
        │   aimvision-backend      │    │   Temporal cluster       │     │  aimvision-ml workers    │
        │   FastAPI · SQLAlchemy   │◀──▶│   (workflow orchestrator)│◀───▶│   GPU pool (A10G/L4)     │
        │   Pydantic · Arq queue   │    │   ADR-0007               │     │   ONNX Runtime · Torch   │
        │   ADR-0001               │    └──────────────────────────┘     │   MLflow registry        │
        └────────────┬─────────────┘                                     └──────────┬───────────────┘
                     │                                                               │
                     ▼                                                               ▼
        ┌──────────────────────────┐                                    ┌──────────────────────────┐
        │  CloudNativePG (Postgres │                                    │  Ollama (LLM, queued)    │
        │  + TimescaleDB + RLS)    │                                    │  fallback: Anthropic API │
        │  ADR-0004 · ADR-0005     │                                    │  feature-flagged         │
        └──────────────────────────┘                                    └──────────────────────────┘
                     │                                                               │
                     ▼                                                               ▼
        ┌──────────────────────────┐                                    ┌──────────────────────────┐
        │  Object store (S3 /      │                                    │  Vector store (pgvector) │
        │  MinIO on-prem) — video, │                                    │  RAG over coach notes    │
        │  models, exports         │                                    │                          │
        └──────────────────────────┘                                    └──────────────────────────┘

                              ┌──────────────────────────────────────────────┐
                              │    TRUST BOUNDARY: Federation on-prem VPN    │
                              └──────────────────────────────────────────────┘
                                                  │
                          ┌───────────────────────┴───────────────────────┐
                          │   Federation appliance (k3s, single Helm)     │
                          │   Same shape: API + workers + CNPG + MinIO    │
                          │   + Ollama + Temporal — no outbound deps      │
                          │   pgBackRest local backup (ADR-0005)          │
                          └───────────────────────────────────────────────┘
```

The three trust boundaries are: (a) **public internet** between the camera/mobile/web clients and the API gateway, terminated with TLS 1.3 and OIDC-bearer auth (Clerk/WorkOS, ADR-0008); (b) **API gateway** as the single ingress to the backend control plane with mTLS to internal services and audit logging on every cross-tenant call; (c) **federation VPN** for on-prem appliances, whose data never leaves the federation network. Detailed isolation rules are in `docs/security/multi-tenant-isolation.md`.

---

## 3. Component responsibilities

### 3.1 aimvision-camera-core (Rust)

A Rust workspace that owns every protocol and time-source concern of every supported capture device. Per ADR-0003, the trait surface is split into `CameraControl` (pairing, settings, lifecycle), `CameraTransport` (BLE, Wi-Fi AP, USB-C UVC), `CameraMedia` (frame and audio handles), `TimeSource` (NTP/PTP/GPS-disciplined clocks), and `CameraCapabilities` (returned at connect time so callers do not call-and-fail on `Unsupported`). Events are a sealed enum with `CameraEvent::Vendor(VendorEvent)` for forward compatibility — never stringly-typed ([Embedded review §Trait Design](reviews/05-embedded-firmware-engineer.md)).

The control plane is exposed to mobile via **UniFFI** (Mozilla, used by `matrix-rust-sdk`, `bitwarden-sdk`, `glean-core`) for structs, enums, async, and traits. The frame-data path uses a hand-written `extern "C"` C ABI consumed by Swift via a bridging header and Kotlin via JNI directly, because UniFFI's zero-copy buffer story is immature ([Mobile review §UniFFI](reviews/04-mobile-app-builder.md)). The `uniffi-rs` minor version is pinned per release; UDL changes have broken iOS+Android bindings simultaneously twice in 2024–2025.

V1 implementations: GoPro Hero 13 over Open GoPro (BLE+Wi-Fi+USB-C UVC). V2-planned: Insta360 X4, custom AIMVISION hardware. The same crate runs on the federation on-prem appliance to drive locally-attached cameras over USB. The architectural justification for Rust is precisely this — three host environments (iOS, Android, Linux x86_64/arm64) with one protocol implementation. **The investment only pays off if V2 hardware or the on-prem appliance materializes**; Phase 2 has an explicit re-evaluation gate (ADR-0003).

### 3.2 aimvision-mobile (React Native)

The athlete app and the in-the-field coach app. **RN 0.76+ with Hermes + Fabric + JSI + TurboModules from Sprint 3** (ADR-0002). The old async JSON bridge is disqualifying for the frame path: the [Mobile review](reviews/04-mobile-app-builder.md) and [Performance review](reviews/10-performance-benchmarker.md) both confirm it would collapse under 24fps frame metadata plus pose keypoints.

Hot path: Rust core delivers decoded frames to a C++ TurboModule (HostObject) that exposes a `JSI::ArrayBuffer` view over native memory; pose keypoints flow through a Reanimated 3 SharedValue to a `@shopify/react-native-skia` canvas on the UI thread. **Reference architecture: react-native-vision-camera v4** — frame processors on a dedicated worklet runtime, pixel buffers as JSI HostObjects. We adopt that pattern wholesale and do not invent a new one.

Threading: a Rust-owned tokio runtime for camera I/O; a hardware-decoder thread (VideoToolbox / MediaCodec async) writing into an `IOSurface`/`AHardwareBuffer` ring buffer; a Core ML / NNAPI inference thread on a separate dispatch queue; the RN UI thread reads only the latest pose tensor via JSI SharedValue and composites with Skia. **No `runOnJS` in the hot path.**

Offline-first storage: **WatermelonDB** with the JSI adapter (Realm's licensing is hostile post-MongoDB acquisition; expo-sqlite is too low-level). Schema: `sessions`, `shots`, `annotations`, `recordings(local_uri, remote_uri, upload_state, sha256)`, `sync_log`. Background uploads use `URLSession`/`WorkManager` with tus.io resumable chunks (5 MB) and on-device SHA-256 dedup.

### 3.3 aimvision-backend (Python + FastAPI)

The cloud-and-on-prem control plane (ADR-0001). **Python 3.12 + FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic + Arq (Redis queue) + Uvicorn behind Granian.** Node.js was rejected because the ML stack (training, ONNX preprocessing, Ollama integration, evaluation harness) is Python; splitting languages would mean reimplementing DTOs, running two CI toolchains, and fragmenting SREs. Pydantic v2 schemas are the source of truth; the frontend gets matching TypeScript types via `openapi-typescript` codegen.

Multi-tenancy is enforced at the database boundary by **Postgres Row-Level Security** keyed on `organization_id`, with an application-layer scope filter as defense-in-depth (ADR-0004). RLS is the floor; the application filter catches developer error before it becomes a cross-tenant leak. Every cross-tenant aggregation (e.g., the federation talent-ID derived report) goes through a dedicated, audited materialized-view pipeline whose proof is in `docs/security/multi-tenant-isolation.md`.

The backend exposes a versioned REST API under `/api/v1`, a WebSocket gateway for live-session feed updates, and signed-URL issuers for direct mobile↔S3 transfer (never proxy video through the API — see [Software Architect review §Scaling Cliffs](reviews/03-software-architect.md)).

### 3.4 aimvision-web (React + TypeScript)

The coach dashboard, federation admin console, and athlete web view. Single-page React with the same Pydantic-derived TypeScript types and the same shared design system as mobile (built on Tamagui or NativeWind with a web target). Authentication is OIDC bearer tokens from Clerk/WorkOS shared across mobile and web. The web app does not have a separate backend; it is a thin client over the same FastAPI gateway. Video playback is via Cloudflare Stream signed URLs.

### 3.5 aimvision-ml (Training + serving)

The ML monorepo. Owns the data labeling pipeline (CVAT integration), the training pipeline (PyTorch with VideoMAE-v2 backbone, RTMPose-x for whole-body pose, multi-label hierarchical diagnostic head per [AI Engineer review §Critical Gaps](reviews/01-ai-engineer.md)), the ONNX export and INT8 quantization scripts, the evaluation harness (per-class macro-F1, ECE, Brier, conformal coverage), and the **MLflow Model Registry** as the system of record for `model_version`. Every prediction in the application database carries a `model_version` foreign key; shadow routing sends 5% of traffic to a candidate model and compares against Franco's labels in a feedback loop.

Inference workers run on a GPU pool (A10G or L4 minimum per [Performance review](reviews/10-performance-benchmarker.md); T4 is too slow for HRNet at full-res). On-device models for live capture are exported via Core ML Tools `cto.coreml.optimize` (INT8 quantization) and NNAPI/TFLite for Android. Quantization decisions are made at training time, not as a Sprint 20 polish step ([Mobile review §Sprint resequencing](reviews/04-mobile-app-builder.md)).

### 3.6 aimvision-infra

The deployment monorepo. **One Helm chart** that deploys the entire stack — API, workers, CloudNativePG, MinIO/S3, Ollama, Temporal — and runs identically on Railway-managed Kubernetes (cloud) and on a federation k3s appliance (ADR-0005). CloudNativePG is the Postgres operator (chosen over Crunchy and Zalando for active development, declarative HA, and Postgres-version parity). Litestream→S3 provides cloud DR; pgBackRest is the on-prem backup. TimescaleDB is enabled as a Postgres extension for V1 longitudinal analytics; ClickHouse is deferred to V2 federation cohort analytics. **No Docker-compose-only on-prem path** — clubs and federations cannot operate it ([Software Architect review §3](reviews/03-software-architect.md)).

---

## 4. Data flows

### 4.1 Live capture (athlete in a session)

1. Mobile pairs Hero 13 over BLE; Rust core opens the Wi-Fi AP and the USB-C UVC tether (federation tier).
2. Hero 13 streams MPEG-TS over UDP/RTP at ~480p/30fps (Wi-Fi) or 1080p UVC (wired).
3. Native decoder (VideoToolbox / MediaCodec) writes to an `IOSurface`/`AHardwareBuffer` ring buffer.
4. On-device audio shot detector (CRNN, ~30 ms p95 on iPhone 13) runs continuously on the audio path.
5. On-device pose (BlazePose Lite or distilled RTMPose-tiny, NPU) runs subsampled at 8–12 fps; YOLOv8n-int8 barrel detection at 5–8 fps.
6. Each _shot event_ is appended to the local WatermelonDB log as an immutable fact: `(session_id, monotonic_seq, device_clock, server_clock, payload)`. **Shot events are append-only and never edited** (ADR-0006). The live feed UI renders by reading the event stream.
7. WebSocket pushes events to the backend in near real time; the backend stores them in the canonical event store.

### 4.2 Post-session pipeline (≤90s p50, ≤150s p95)

A **Temporal workflow** (ADR-0007) orchestrates the pipeline as a DAG of idempotent activities:

1. Mobile finalizes upload of the recording via tus.io to S3 (signed URL, never proxied through API).
2. Temporal `ProcessSessionWorkflow(session_id, recording_id)` fires.
3. Activities: `ReFetchAndDecode` → `RunWholeBodyPose` (HRNet/RTMPose-x on GPU) → `RunBarrelDetector` → `RunDiagnosticEnsemble` → `GenerateLLMReport` (Ollama queued, fallback Anthropic) → `RenderPDF` → `NotifyAthlete`.
4. The post-session report is a **CQRS projection** rebuilt from the shot event stream plus the GPU re-analysis. It is recomputable; if a model version updates, we simply replay.
5. Per [Performance review](reviews/10-performance-benchmarker.md), the LLM stage uses a 14B Q4_K_M model on A10G (~14–22 s); 32B is rejected on cost grounds.

### 4.3 Longitudinal analytics

A **second Temporal-driven projection** over the same shot event stream populates TimescaleDB hypertables for per-athlete trend analysis. EPIC 14 reads from this projection; it never re-aggregates from the source events on the read path. ClickHouse is the V2 path for federation-wide cohort analytics.

### 4.4 QR check-in (Club tier)

A coach-issued **PASETO v4.local** token (chosen over JWT to eliminate algorithm confusion, with smaller payload) is rendered as a QR code with `exp=30s`, `aud=club:<id>`, `scope=checkin`, single-use `jti` tracked server-side. Athlete scans → mobile presents to backend → backend verifies and registers the session. Detail in `docs/security/qr-check-in.md`.

---

## 5. Multi-tenancy and isolation

Three isolation strata, increasing in strength:

1. **Cloud Solo/Club:** shared Postgres database, shared schema. Tenant boundary enforced by Postgres RLS on `organization_id` plus an application-layer scope filter. Suitable for tens of thousands of small tenants. (ADR-0004)
2. **Cloud Federation (managed but isolated):** dedicated logical database within the same CloudNativePG cluster. Federation can be migrated to a dedicated cluster on demand without code changes.
3. **Federation on-prem:** an entire copy of the Helm chart on a k3s appliance inside the federation's network. No outbound dependency on the cloud control plane. Local Ollama, local Postgres, local MinIO, local Temporal.

Cross-tenant data flows (e.g., the federation talent-ID report that aggregates club data inside one federation) go through a single audited pipeline owned by the backend; there is no ad-hoc cross-tenant query path. The full proof is in `docs/security/multi-tenant-isolation.md` ([Compliance auditor review](reviews/07-compliance-auditor.md) cites GDPR data-residency obligations that this satisfies).

---

## 6. Cloud↔on-prem parity model

Parity is enforced by deployment shape, not by code branching. The same Helm chart, the same container images, and the same database schema run in both environments. Differences are configuration:

- **Cloud:** Railway-managed k8s, Cloudflare Stream/Mux for video CDN, Clerk/WorkOS for auth, S3 for object store, Litestream for DR, hosted Anthropic/Together LLM fallback.
- **On-prem:** k3s on a single appliance (or a 3-node cluster for federation HA), MinIO for object store, on-appliance Ollama only, pgBackRest for backups, no CDN (LAN-only video delivery).

Sprint 17's "validate on-prem deployment" becomes a one-day acceptance test instead of a two-week port. The on-prem appliance ships with a tested firmware matrix for the cameras it manages (per [Embedded review §Critical Things Missing](reviews/05-embedded-firmware-engineer.md), pinned camera firmware versions).

---

## 7. Build vs buy summary

The complete catalog with vendor names, cost-tier guesses, and rationale is in **ADR-0008**. Headline: we **buy** auth (Clerk or WorkOS — Apple/Google/email/SAML for federations), payments (Stripe + RevenueCat), video CDN (Cloudflare Stream or Mux), errors (Sentry), logs/metrics/traces (Grafana Cloud or Axiom), feature flags (Statsig or PostHog), OTA (Expo EAS Update), annotation (CVAT), inference (ONNX Runtime), and the model registry (MLflow). We **build** the camera core (justified only if V2 hardware lands, ADR-0003), the ML models (the moat), the LLM coaching prompt + structured-output verifier, the multi-tenant orchestration, and QR check-in. **We never proxy video through the API** — that is a hard architectural rule because S3 egress through the API would dominate cost by Sprint 19 ([Software Architect review §Scaling Cliffs](reviews/03-software-architect.md)).

---

## 8. Cross-cutting concerns

- **Observability.** OpenTelemetry from Sprint 6, not Sprint 22 ([Performance review §Instrumentation](reviews/10-performance-benchmarker.md)). Span per ML stage on-device exported via OTLP/HTTP. Sentry for errors, Sentry Performance + Firebase Performance Monitoring on mobile, Grafana Cloud or Axiom for backend logs/metrics/traces, Datadog APM optional. Per-stage histograms (p50/p95/p99) for `wifi_preview_lag`, `decode_lag`, `pose_lag`, `classifier_lag`, `bridge_lag`, `shot_to_feed_lag`. A debug overlay surfaces these in dev builds from Sprint 7. A nightly synthetic load rig (phone-on-tripod replaying recorded fixture sessions) asserts p95 budgets in CI from Sprint 8.
- **Feature flags.** Statsig or PostHog from Sprint 3. Required to dark-launch the diagnostic classifier, A/B coach-mode tone variations, gate tier features, and toggle the LLM fallback (Ollama → Anthropic) without redeploying.
- **OTA.** Expo EAS Update from Sprint 5 (CodePush is being sunset by Microsoft). Egypt validation cannot wait 2–7 days for App Store review on a hotfix.
- **Secrets.** GCP Secret Manager or AWS Secrets Manager in cloud; HashiCorp Vault on the federation appliance. No secrets in env files committed to git. Secret rotation is automated via Temporal scheduled workflows.
- **Audit logging.** Append-only audit log table (separate from the operational Postgres) for every cross-tenant access, every authentication event, every model version change, every data-erasure execution. Forwarded to Grafana Cloud / Axiom for retention. Detailed schema in `docs/security/audit-logging.md`.
- **Privacy and compliance.** GDPR / Egypt PDPL right-to-erasure is implemented as a Temporal `ErasureWorkflow` that fans out to every owned data store (Postgres, S3, MLflow training-data lineage, vector store, search index). The workflow is idempotent and audited. Detail in `docs/compliance/gdpr-erasure-flow.md`.
- **Data residency.** Cloud tenants are pinned to a region at signup and never migrated cross-region without an explicit signed contract. Federation on-prem trivially satisfies residency.

---

## 9. References

**Reviews (the input critique that this architecture answers):**

- [01 — AI Engineer](reviews/01-ai-engineer.md) — ML stack: RTMPose-x, VideoMAE-v2, multi-label hierarchical head, calibration, conformal prediction.
- [02 — Trend Researcher](reviews/02-trend-researcher.md) — competitive frame, federation flywheel as moat, GTM gaps.
- [03 — Software Architect](reviews/03-software-architect.md) — UniFFI tradeoffs, FastAPI choice, CloudNativePG, event sourcing, Temporal.
- [04 — Mobile App Builder](reviews/04-mobile-app-builder.md) — RN New Architecture, Skia overlay, WatermelonDB, tus.io, OTA.
- [05 — Embedded Firmware Engineer](reviews/05-embedded-firmware-engineer.md) — Open GoPro reality, multi-cam sync, trait split, firmware pinning.
- [06 — Security Engineer](reviews/06-security-engineer.md) — auth, audit, secrets, threat model.
- [07 — Compliance Auditor](reviews/07-compliance-auditor.md) — GDPR, Egypt PDPL, App Store firearms policy.
- [08 — UX Researcher](reviews/08-ux-researcher.md) — accessibility, RTL, i18n.
- [09 — Sprint Prioritizer](reviews/09-sprint-prioritizer.md) — sprint resequencing.
- [10 — Performance Benchmarker](reviews/10-performance-benchmarker.md) — latency budgets, GPU sizing, instrumentation.

**Architecture Decision Records:**

- [ADR-0001 — Backend on Python + FastAPI](adr/0001-backend-python-fastapi.md)
- [ADR-0002 — Mobile on RN New Architecture (Hermes/Fabric/JSI)](adr/0002-mobile-rn-new-architecture.md)
- [ADR-0003 — Rust camera-core trait split (UniFFI control / extern "C" media)](adr/0003-rust-camera-core-split.md)
- [ADR-0004 — Multi-tenancy via Postgres RLS](adr/0004-multi-tenancy-rls.md)
- [ADR-0005 — CloudNativePG + single Helm chart for cloud↔on-prem parity](adr/0005-cloudnativepg-cloud-onprem-parity.md)
- [ADR-0006 — Event sourcing for shot events](adr/0006-event-sourcing-shot-events.md)
- [ADR-0007 — Temporal for workflow orchestration](adr/0007-temporal-orchestration.md)
- [ADR-0008 — Build vs buy](adr/0008-build-vs-buy.md)

**Companion docs (predicted filenames; owned by other reviewers):**

- `docs/security/multi-tenant-isolation.md`
- `docs/security/threat-model.md`
- `docs/security/audit-logging.md`
- `docs/security/qr-check-in.md`
- `docs/compliance/gdpr-erasure-flow.md`
- `docs/compliance/app-store-firearms-positioning.md`
- `docs/operations/runbooks/`
- `docs/ml/model-registry-and-shadow-eval.md`
