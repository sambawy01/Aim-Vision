# AIMVISION — V2 Sprint Build Plan

**Owners:** Franco Donato (Founder/CEO), Hany Sadek (CTO)
**Format:** Sequential sprints, no fixed durations. Sprints close when [GATE] criteria are measurably met.
**Document Version:** 2.0 — supersedes `AIMVISION_V1_Sprint_Build_Plan.txt` v1.0
**Date:** 2026-05-06

---

## What changed from V1

This V2 plan integrates the ten specialist reviews under `docs/reviews/01-...md` through `10-...md`. Every structural change below cites the originating reviewer.

- **Federation-first sequencing.** Coach/Org/Cohort schema, joint-controller agreements, and audit logging move from Sprint 13/17 into Sprint 4–6. Solo is rebuilt as a constrained subset of the coach data model, not the other way around. *Per Software Architect review (#3), Sprint Prioritizer review (#9), Compliance Auditor review (#7).*
- **Telemetry, observability, and OTA pulled to Sprint 3–4.** Sentry, feature flags, EAS Update OTA, PrivacyInfo manifest, battery and thermal instrumentation all instrumented before first Egypt capture. *Per Performance Benchmarker review (#10), Sprint Prioritizer review (#9).*
- **IMU integrated in V1, not V2.** A BLE gun-stock IMU (MPU-6050 / BMI270 class, ~$15 BOM) becomes a P1 deliverable in Sprint 10 with feature-flagged rollout. *Per AI Engineer review (#1) and Embedded Firmware Engineer review (#5).*
- **MediaPipe Pose replaced.** RTMPose-x (with MMPose Wholebody for hands/face) is the V1 pose backbone by Sprint 8. SAM2 segmentation tracks barrel-plus-shooter through occlusion. *Per AI Engineer review (#1).*
- **Multi-task hierarchical diagnostic head.** The single multiclass classifier in V1 is replaced by per-branch experts (head/eye, mount/stance, swing/lead, follow-through) with temperature scaling, conformal prediction, and per-class abstention thresholds — landing Sprint 9. *Per AI Engineer review (#1).*
- **VideoMAE-v2 self-supervised pretraining + ActionFormer temporal head.** Burns no Franco labels for backbone; weak supervision via audio-anchored windows. *Per AI Engineer review (#1).*
- **USB-C tethered preview is P0 for the federation tier**, not P1 investigation. Wi-Fi preview is reframed as the Solo path with honest 1.5–4 s latency targets; USB-C is the coaching-grade path at p50 ≤ 1.2 s. *Per Embedded Firmware Engineer review (#5), Performance Benchmarker review (#10).*
- **GoPro Labs firmware decision moved to Sprint 2.** Federation tier needs `!MSYNC` and scheduled capture; commit or refuse Labs in Phase 0 rather than Sprint 17. *Per Embedded Firmware Engineer review (#5).*
- **Pinned firmware matrix and startup compatibility check** added Sprint 4. *Per Embedded Firmware Engineer review (#5).*
- **Microphone array (4-mic, ~$30) and gaze tracking (L2CS-Net + 6DRepNet) added as P1** — multi-shooter audio attribution and gaze-leads-head signal. *Per AI Engineer review (#1).*
- **Spanish localization dropped from V1.** RTL Arabic + accessibility primitives kept and pulled to Sprint 3. Spanish deferred to V1.5. *Per Sprint Prioritizer review (#9), UX Researcher review (#8).*
- **On-prem federation deployment validation deferred to V1.5.** Architecture stays portable but Egypt runs on managed cloud (EU region). *Per Sprint Prioritizer review (#9), Performance Benchmarker review (#10).*
- **Whoop / Oura / HealthKit stubs deferred to V1.5.** Validity study protocol is pulled forward from V2. *Per Sprint Prioritizer review (#9).*
- **Multi-camera-sync-at-rig becomes architecture-only in V1.** Two-camera capture lives in V1.5; one camera + audio cross-correlation backbone is V1. *Per Embedded Firmware Engineer review (#5), Sprint Prioritizer review (#9).*
- **Cross-discipline scaffolding for trap and sporting clays** (data model, taxonomy) added in Sprint 15. *Per Trend Researcher review (#2).*
- **Phase 0 compliance work front-loaded.** DPO appointed Sprint 1; PDPC license filed Sprint 1; EU+Egyptian counsel engaged Sprint 1; threat model and data classification table embedded in architecture doc Sprint 2. *Per Compliance Auditor review (#7).*
- **Age gate + verifiable parental consent** lives in Sprint 3, before any Egypt capture. *Per Compliance Auditor review (#7).*
- **DPIA completed before Sprint 5.** First Egypt session is gated on it. *Per Compliance Auditor review (#7).*
- **WatermelonDB + sync engine in Sprint 5** (not Sprint 12). Offline-first is foundational, not polish. *Per Mobile App Builder review (#4).*
- **Audit logging from Sprint 1** for a minimum event set (auth, consent, data access). *Per Compliance Auditor review (#7).*
- **App Store TestFlight + early Apple/Google engagement in Sprint 6.** Firearms-content positioning rehearsed in writing 16+ sprints before submission. *Per Sprint Prioritizer review (#9).*
- **Wizard-of-Oz LLM coaching notes in Sprint 6–7.** Franco hand-writes the structured outputs; LLM is plumbed in Sprint 11 against frozen examples. *Per UX Researcher review (#8).*
- **Range Mode UX commitment** locked in Phase 0. Outdoor sun-readable, glove-friendly, large-tap-target variant of every primary screen. *Per UX Researcher review (#8), Embedded review (#5).*
- **JSI / Fabric / Hermes commitment locked.** React Native New Architecture, no legacy bridge for any frame-data path. *Per Software Architect review (#3), Mobile App Builder review (#4).*
- **Backend stack: Python + FastAPI committed.** Type-stub'd, OpenAPI codegen to clients, async-first. *Per Software Architect review (#3).*
- **Phase gates rewritten as measurable objectives** — latency, accuracy with denominators, calibration error, frame-drop rates. *Per Sprint Prioritizer review (#9), Performance Benchmarker review (#10).*
- **Hire timing staggered.** Core engineering hiring closed by Sprint 7. Second annotator-coach by Sprint 6 (Franco's annotation throughput is the true critical path, not camera core). Part-time SRE by Sprint 10. Designer full-time by Sprint 6. DPO Sprint 1. *Per Sprint Prioritizer review (#9), AI Engineer review (#1).*
- **Stop-the-line rules** explicit per phase (e.g., diagnostic accuracy < 60% at Sprint 9 → halt feature work). *Per Sprint Prioritizer review (#9).*
- **Risk register expanded R16–R25.** Compliance R16–R19 plus performance / firmware / RN-bridge / first-party-threat / incumbent-pivot / geopolitical R20–R25. *Per reviews #4, #5, #6, #7.*
- **Penetration test in Sprint 21; SOC 2 Type II observation window opens Sprint 19; SOC 2 Type I report Sprint 24; bug bounty + responsible disclosure Sprint 22.** *Per Compliance Auditor review (#7), Security Engineer review (#6).*
- **Secondary Western design partner committed before public launch** to derisk Egypt-only optics. *Per Trend Researcher review (#2).*

Cross-references throughout cite ADRs and specs being authored in parallel under `docs/architecture/`, `docs/security/`, `docs/ml/`, `docs/compliance/`. They are predicted to exist by the time this plan is consumed.

---

## 0. How to read this plan

**Structure:** PHASE → SPRINT → EPIC → STORY.

**Markers:** `[P0]` critical path; `[P1]` important, can slip without major impact; `[P2]` first to cut; `[DEP]` external dependency; `[RISK]` flag in retro; `[GATE]` measurable phase-gate criterion.

**Tracks (six, parallel):**

| Track | Scope |
|---|---|
| TRACK-CORE | Rust camera abstraction core (UniFFI) |
| TRACK-MOBILE | RN iOS + Android app (New Arch / JSI / Fabric / Hermes) |
| TRACK-WEB | Coach + Federation web dashboard (React) |
| TRACK-ML | Model training, inference, diagnostic pipeline |
| TRACK-BACKEND | Python + FastAPI services, Postgres, S3 |
| TRACK-DATA | Annotation, datasets, validity study |

Sprints close when [GATE] criteria are measurably met. Velocity is observed retrospectively, not promised in advance.

---

## 1. Team assumptions (V2 hire ladder)

| Role | Hire by | Notes |
|---|---|---|
| Founder/CEO/Domain (Franco) | S1 | Critical-path constraint = annotation throughput |
| CTO (Hany) | S1 | |
| DPO | S1 | Required by Egypt PDPL Art. 8; cannot be combined with CTO. *Per Compliance review (#7)* |
| Rust Engineer (Camera Core) | S2 | KMM as fallback if Rust hire slips |
| RN Lead (New Arch) | S2 | JSI/Fabric/Hermes proficiency required |
| ML Engineer | S3 | |
| Backend Engineer (Python/FastAPI) | S3 | |
| Designer | S6 (full-time) | Range-Mode UX commitment |
| Annotator-coach #2 | S6 | Critical-path expansion of Franco's labelling capacity |
| Mobile Engineer (native modules) | S7 | |
| ML/CV Specialist (3D, IMU fusion) | S7 | |
| Web Engineer (React) | S7 | |
| Part-time SRE | S10 | Observability, incident response, on-call rotation |
| QA / Annotator scaling | S10 onwards | |

External: EU privacy counsel (S1), Egyptian counsel (S1), product-liability insurance broker (S2), pen-test firm (CREST/OSCP) (S20), SOC 2 auditor (S14).

---

## 2. Phase overview

| Phase | Sprints | Theme |
|---|---|---|
| 0 | 1–2 | Compliance, hiring, architecture, observability scaffolding |
| 1 | 3–6 | Federation-first foundations, single-camera capture, audio + pose backbone, Egypt capture begins |
| 2 | 7–12 | Coach OS first; Solo as subset. Live coaching feed, post-session report, IMU integration |
| 3 | 13–18 | Longitudinal analytics, drill library, QR check-in, federation admin, RTL/a11y, validity study collection, SOC 2 controls |
| 4 | 19–21 | Egypt validation, accuracy tuning, beta program, pen test, SOC 2 Type II observation window |
| 5 | 22–24 | Pre-launch polish, bug bounty, public launch, SOC 2 Type I report |

---

## 3. Critical path correction

V1's critical path treated camera core as the hardest dependency. V2 corrects this: the actual critical path runs through Franco's annotation throughput, schema decisions made in Sprint 4, App Store firearms-policy review, and DPIA-before-Egypt.

**Ordered V2 critical path (each blocks the next):**

1. Compliance gate: DPO + PDPC license filing + counsel engaged + DPIA scoped (S1–S2). *Per Compliance review (#7).*
2. Architecture gate: threat model, data classification, JSI/Fabric/Hermes commitment, FastAPI commitment, federation-first schema designed (S2). *Per Software Architect review (#3).*
3. Observability + age gate + parental consent live in app shell (S3). *Per Compliance + Sprint Prioritizer reviews.*
4. Coach/Org schema + audit logging + WatermelonDB sync engine (S4–S5). *Per Architect, Mobile, Compliance reviews.*
5. DPIA signed → first Egypt capture (S5).
6. Annotator #2 onboarded (S6) → labelling throughput unblocks ML (S7+). *Per AI Engineer + Sprint Prioritizer reviews.*
7. App Store early-engagement letter sent + TestFlight up (S6). *Per Sprint Prioritizer review (#9).*
8. RTMPose-x baseline beats MediaPipe on shooting test set (S8) → diagnostic pipeline.
9. Multi-task hierarchical diagnostic head + calibration (S9) → live feed v1 (S10) → post-session report (S11).
10. IMU integration P1 landing (S10) → 3D pose deferral risk reduced.
11. Closed beta + validity study collection (S21).
12. SOC 2 Type I report (S24) → federation procurement unblocked.

**Hidden dependencies surfaced by reviewers:**

- **Franco's annotation rate** (R9 in V1) is the real ML critical path, not GPU time. Mitigated by S6 hire of annotator-coach #2, active learning queue (BALD/coreset), VideoMAE pretraining that needs no labels.
- **Schema decisions in S4** (Coach/Org/Cohort/Membership/Consent) bind federation, club, and Solo paths together. Wrong call here = S13–S17 refactor.
- **App Store firearms policy** has 4–6 week review cycles for novel categories. Engagement starts S6, not S22.
- **DPIA-before-Egypt** is a legal, not engineering, dependency. If counsel slips, S5 slips. Owner: DPO + CEO.

---

## 4. Sprint-by-sprint plan

### PHASE 0 — FOUNDATION

#### SPRINT 1 — Company, Compliance, DPO, Counsel

**Goal:** Legal entity exists; compliance program kicked off; first engineering offers out; minimum audit logging skeleton committed.

**EPIC 1.1 Company Formation**
- [P0] Incorporate (Delaware C-corp + Egypt branch entity for PDPL local presence; counsel-confirmed).
- [P0] Founders' agreement, equity, vesting, IP assignment.
- [P0] Cap table, bank, payment processing.
- [P1] Trademark filings (US, EU, Egypt); domain consolidation.
- [P2] Insurance research: cyber liability + product liability + professional indemnity (USD 5M minimum target). *Per Compliance review (#7).*

**EPIC 1.2 Compliance Kickoff** *(per Compliance Auditor review #7)*
- [P0] **DPO appointed** — independent, not CTO; Egypt-locally accessible per PDPL Art. 8.
- [P0] **EU privacy counsel engaged** (GDPR + UK Children's Code).
- [P0] **Egyptian counsel engaged** (Law 151/2020 PDPL).
- [P0] **PDPC license application filed** (processor + biometric/health tier).
- [P0] **Cross-border transfer permit application filed** (Egypt → EU/US data flow).
- [P0] DPIA scoped with EU counsel; draft started.
- [P0] Joint-controller agreement template drafted (GDPR Art. 26) for Egypt federation + future clubs.
- [P1] Article 30 RoPA template started.

**EPIC 1.3 Egypt Design Partner Agreement**
- [P0] Egypt National Team agreement signed (data use, IP, exclusivity, consent, ministerial sign-off path for minors).
- [P0] **Athlete consent flow drafted as separable, granular, withdrawable per Article 9 GDPR + PDPL** (coaching, ML training, marketing case study each separate). *Per Compliance review (#7).*
- [P0] **Verifiable parental consent flow scoped** for minors (email-plus-ID or signed PDF; not checkbox).
- [P0] Ministry of Youth and Sports authorization request initiated for junior team data.

**EPIC 1.4 Initial Hiring**
- [P0] JDs for Rust, RN Lead, ML, Backend, DPO published.
- [P0] Recruiting channels active.
- [P0] Interview rubrics documented; structured interview process.
- [P1] Designer (full-time) and annotator-coach #2 search active.

**EPIC 1.5 Engineering Environment + Minimum Audit Logging**
- [P0] GitHub org; repo structure; protected main; signed commits required.
- [P0] CI/CD: GitHub Actions; secrets management (GitHub Encrypted Secrets + Doppler).
- [P0] Linear for project management; Notion for docs.
- [P0] Slack + 1Password + 2FA enforced.
- [P0] **Minimum audit logging committed** (auth events, consent events, data-access events) into a write-only append log. *Per Compliance review (#7).*
- [P1] Initial security baselines documented.

**[GATE] Sprint 1 measurable criteria:**
- Company exists with funded bank account and signed counsel engagement letters (EU + Egypt).
- DPO contract signed; PDPC license application receipt obtained.
- DPIA scope agreed with counsel in writing.
- Egypt agreement signed including separable Art. 9 / PDPL consent.
- ≥ 5 candidate interviews scheduled across Rust, RN, ML.
- Audit-logging schema committed to repo.

---

#### SPRINT 2 — Architecture, Threat Model, Stack Commitments

**Goal:** Architecture document complete with threat model and data classification table; stack commitments locked; first 2 engineers contributing; office test rig running with pinned firmware.

**EPIC 2.1 Architecture Document — V2** *(per Architect review #2)*
- [P0] Master architecture doc (`docs/architecture/master.md`).
- [P0] **Threat model document** (`docs/security/threat-model.md`) — STRIDE on each trust boundary; Egypt cross-border data flow modelled. *Per Compliance review (#7).*
- [P0] **Data classification table** embedded in architecture doc — Article 9 biometric, health, minor, financial, ordinary. Each row: storage location, access roles, retention, deletion path. *Per Compliance review (#7).*
- [P0] Camera abstraction interface specified — split into `CameraControl` + `CameraTransport` + `CameraMedia` + `TimeSource` + capability-typed events. *Per Embedded review (#5).*
- [P0] **Federation-first data model:** Account → User → Membership → Org (Federation/Club/Solo as Org subtypes) → Cohort → AthleteProfile → Session → Recording → Shot → Annotation → ConsentRecord. Solo derives via constrained Org. *Per Architect + Sprint Prioritizer reviews.*
- [P0] ML pipeline architecture — VideoMAE pretrain, RTMPose-x, hierarchical diagnostic head, calibration, abstention. *Per AI Engineer review (#1).*
- [P0] Mobile architecture — RN New Arch (Fabric + JSI + Hermes); no legacy bridge on any frame path. *Per Mobile review (#4), Software Architect review (#3).*
- [P0] Backend architecture — **Python + FastAPI**, Pydantic models, OpenAPI codegen to mobile + web, async workers via Arq/Dramatiq. *Per Software Architect review (#3).*
- [P0] Cloud infra — EU-region Railway + S3-compatible object storage; Egypt mirror deferred to V1.5 per scope cut.
- [P0] **GoPro Labs firmware decision: COMMIT** to Labs for federation tier (`!MSYNC`, scheduled capture, QR control). Solo tier stays stock. *Per Embedded review (#5).*
- [P0] **USB-C P0 for federation tier:** UVC 1080p webcam mode is the coaching-grade preview path. Wi-Fi is Solo only. *Per Embedded + Performance reviews.*
- [P0] **Range Mode UX commitment** — sun-readable, glove-friendly, large-tap variant of every primary screen documented in design system. *Per UX review (#8).*
- [P1] Internationalization plan — English + Arabic + RTL primitive in V1; Spanish deferred. *Per Sprint Prioritizer review (#9).*

**EPIC 2.2 Repos and CI**
- [P0] Repos: `aimvision-camera-core` (Rust), `aimvision-mobile` (RN New Arch), `aimvision-backend` (Python/FastAPI), `aimvision-web` (React/Vite), `aimvision-ml` (PyTorch/MMPose).
- [P0] CI on each: lint, type-check, test, build; protected main; required reviews.
- [P0] **Pre-merge SAST** (Semgrep) and dependency scanning (Dependabot + Snyk free tier).
- [P0] **Secrets-scanning pre-commit hook** (gitleaks).
- [P1] Documentation site (mdBook or Docusaurus) for internal architecture.

**EPIC 2.3 First Engineering Hires Onboarded**
- [P0] Rust engineer onboarded; environment up.
- [P0] RN Lead onboarded; New Arch sample project building.
- [P1] ML and Backend offers extended.

**EPIC 2.4 Office Test Rig + Pinned Firmware Matrix** *(per Embedded review #5)*
- [P0] 2× Hero 13 + Media Mod + ChArUco calibration board + tripods (Manfrotto 055-class) + 5GHz AP-only test environment.
- [P0] **Pinned firmware matrix** committed: `{Hero 13 firmware vX.Y.Z → Labs firmware vA.B → app version}` with known-good combinations. Startup compatibility check skeleton committed.
- [P0] White silicone sleeves + foam windscreens spec'd as consumables.
- [P0] USB-C PD power banks (≥20Ah, 30W+) + powered USB-C hubs spec'd for operator station.
- [P1] Recorded fixture sessions captured for development use.
- [P1] Mock camera spec written including fault-injection grammar (`drop_wifi`, `ble_disconnect`, `thermal_warn`, `battery_low`).

**[GATE] Sprint 2 measurable criteria:**
- Architecture doc reviewed and approved by CTO + DPO + Founder (signed-off in repo).
- Threat model and data classification table merged.
- All five repos CI-green on initial commit.
- Hero 13 office rig connects on pinned firmware; startup check rejects an out-of-matrix firmware.
- ≥ 2 engineers actively contributing (≥ 5 merged PRs).

---

### PHASE 1 — FEDERATION-FIRST FOUNDATIONS

#### SPRINT 3 — Camera Core, Mobile Shell, Observability, Age Gate

**Goal:** Camera trait + mock + first BLE/HTTP path on real Hero 13. RN shell with i18n + RTL + a11y primitives, age gate, parental consent, Sentry, feature flags, EAS Update, PrivacyInfo manifest, battery + thermal instrumentation. Backend skeleton with auth + audit logging.

**EPIC 3.1 Rust Camera Core Skeleton (TRACK-CORE)** *(per Embedded review #5)*
- [P0] `CameraControl` + `CameraTransport` + `CameraMedia` + `TimeSource` traits defined.
- [P0] `CameraCapabilities` returned at connect time (live preview? Hilight? external trigger? UVC?).
- [P0] Capability-typed `CameraEvent` enum with `CameraEvent::Vendor(_)` escape hatch.
- [P0] Connection state machine + error taxonomy.
- [P0] Mock camera + fixture playback with **fault-injection YAML grammar**.
- [P0] In-Rust command queue: single in-flight, 2 s watchdog. *Per Embedded review (#5).*

**EPIC 3.2 Open GoPro Real-Hardware Prototyping (TRACK-CORE)**
- [P0] BLE pairing flow on Hero 13 with **explicit forget-on-both-ends recovery** (BLE service `0xb5f9` Unpair + iOS CoreBluetooth bond clear). *Per Embedded review (#5).*
- [P0] HTTP API client over Wi-Fi (5 GHz forced).
- [P0] Thermal-state poll wired into Camera trait. *Per Embedded review (#5).*
- [P0] **USB-C UVC transport prototyped** (federation-tier P0). *Per Embedded review (#5).*
- [P1] Multi-camera sync investigation begins (deferred build to V1.5).

**EPIC 3.3 Mobile App Shell (TRACK-MOBILE)** *(per Mobile review #3, Sprint Prioritizer review #8)*
- [P0] RN + TypeScript + **New Architecture (Fabric + JSI + Hermes) confirmed building on iOS + Android**.
- [P0] Navigation (React Navigation v7 with native stack).
- [P0] State management: Zustand + Reanimated v3.
- [P0] **i18n framework (i18next) with English + Arabic from day one; RTL layout primitives, mirror utilities, bidi text input**. *Per Sprint Prioritizer + UX reviews.*
- [P0] **Accessibility primitives**: WCAG 2.1 AA color contrast tokens, dynamic type, screen-reader labels enforced via lint rule.
- [P0] **Sentry SDK installed** with PII scrubbing; release-tagged.
- [P0] **Feature flags (Statsig or self-hosted Unleash)** wired before any product code.
- [P0] **EAS Update OTA** configured; staged rollout policy documented.
- [P0] **PrivacyInfo.xcprivacy manifest** + Android Data Safety draft committed.
- [P0] **Battery + thermal instrumentation** — `UIDevice.batteryLevel`/Android BatteryManager + `ProcessInfo.thermalState`/Android thermal listener — surfaced to Sentry breadcrumbs.
- [P0] **Age gate** at signup with DOB; branching flows under-13 / under-16 / under-18. *Per Compliance review (#7).*
- [P0] **Verifiable parental consent flow** (email-plus-ID + signed PDF path). *Per Compliance review (#7).*
- [P1] Range-Mode design tokens stubbed.

**EPIC 3.4 Backend Skeleton (TRACK-BACKEND)**
- [P0] Python + FastAPI scaffolded with Pydantic; OpenAPI generated.
- [P0] Postgres on Railway (EU region); migrations via Alembic.
- [P0] Federation-first schema migration #1: Account, User, Membership, Org, Cohort, AthleteProfile, **ConsentRecord** (Art. 9 separable consent rows). *Per Architect + Compliance reviews.*
- [P0] Auth service: JWT issuance, refresh, Apple/Google sign-in.
- [P0] **Audit-logging service live** with append-only event log (auth, consent, data-access). *Per Compliance review (#7).*
- [P1] S3-compatible object storage configured.
- [P1] Health checks + structured logging.

**EPIC 3.5 Data Infrastructure (TRACK-DATA)**
- [P0] CVAT instance deployed (EU region, behind VPN, audit-logged).
- [P0] Annotation taxonomy v0 defined for shooting (skeet primary).
- [P0] **Active-learning queue scaffold** (BALD/coreset selection planned, stubbed). *Per AI Engineer review (#1).*
- [P1] Sample annotation workflow documented for Franco.

**[GATE] Sprint 3 measurable criteria:**
- Mock camera replays a fixture and survives an injected `drop_wifi` event without orphaning state.
- Real Hero 13 pairs over BLE on pinned firmware; force-unpair recovery passes.
- RN app builds on iOS 17 + Android 14 simulators with New Arch enabled; Hermes on; Sentry receives a test event; a flagged feature can be toggled live.
- App refuses signup without DOB; under-18 path requires verifiable parental consent before proceeding.
- Backend audit log captures every auth + consent event, queryable.
- CVAT accessible to Franco for trial annotation.

---

#### SPRINT 4 — Real Camera, Federation Schema, Native Bridges, App-Store Pre-Engagement

**Goal:** Real Hero 13 records and downloads. Federation-tier schema (Coach/Org/Cohort/Membership) lands. UniFFI iOS + JNI Android native modules expose Rust core to RN over JSI. Apple/Google early-engagement letters drafted.

**EPIC 4.1 Open GoPro Recording Lifecycle (TRACK-CORE)**
- [P0] BLE + Wi-Fi production code path: settings, start/stop, file list, file download.
- [P0] Reconnection logic exercised against drop_wifi, ble_disconnect, thermal_warn, battery_low fault injections.
- [P0] Status polling + state observation; thermal-state derate ladder hooked.
- [P0] **`camera_clock_offset_ms` baked into the Recording schema now**, not Sprint 17. *Per Embedded review (#5).*
- [P1] USB-C UVC live preview path online for federation tier.

**EPIC 4.2 Native Module Bridges (TRACK-CORE + TRACK-MOBILE)** *(per Architect + Mobile reviews)*
- [P0] iOS Swift module wrapping Rust core via UniFFI; **exposed to RN via JSI HostObject, not legacy bridge**.
- [P0] Android Kotlin module wrapping Rust core via JNI; **exposed via Fabric TurboModule**.
- [P0] First end-to-end JSI call: RN → Rust → response in ≤ 5 ms warm.

**EPIC 4.3 Federation-First Schema Migration (TRACK-BACKEND)** *(per Architect + Sprint Prioritizer reviews)*
- [P0] Migration #2: Org (Federation/Club/Solo subtypes), Cohort, CoachProfile, AthleteProfile, Membership with role enum (athlete, coach, admin, federation-admin, parent-guardian).
- [P0] Migration #3: Session, Recording, Shot, ShotEvent, Annotation, AnnotationVisibilityScope.
- [P0] **Joint-controller-aware ConsentRecord** — Art. 26 GDPR — captures controller IDs, purposes, withdrawal events. *Per Compliance review (#7).*
- [P0] Authorization layer with role-based access control + ABAC for cross-org reads.
- [P0] **API contract codegen** to mobile + web from OpenAPI.

**EPIC 4.4 ML Onboarding + Backbone Selection (TRACK-ML)** *(per AI Engineer review #1)*
- [P0] ML engineer onboarded.
- [P0] **RTMPose-x committed as V1 pose backbone**; MediaPipe used only as smoke-test baseline.
- [P0] MMPose Wholebody (133 keypoints) integration scoped.
- [P0] ONNX Runtime + ONNX/INT8 quantization plan committed (mobile and server). *Addresses AI review #1's hardware/quantization gap.*
- [P0] Ollama instance deployed; **DeepSeek + lighter fallback model** evaluated.
- [P1] VideoMAE-v2 pretraining environment scoped.

**EPIC 4.5 Design Sprint: Wireframes (TRACK-MOBILE)**
- [P0] Designer onboarded full-time (target by S6 latest).
- [P0] IA review with Franco + Hany + DPO.
- [P0] Wireframes for primary mobile flows: onboarding, age gate, parental consent, home, session start, **Range Mode** variants. *Per UX review (#8).*
- [P1] Wireframes for live session screen + post-session report.

**EPIC 4.6 App-Store Early Engagement** *(per Sprint Prioritizer review #8)*
- [P0] Engagement letter drafted to Apple App Review and Google Play Trust & Safety positioning AIMVISION as **Olympic shooting-sports training** (not firearms operation).
- [P0] TestFlight scaffolding configured (internal testers only at this stage).

**[GATE] Sprint 4 measurable criteria:**
- Real Hero 13 starts/stops recording on command; file download succeeds; reconnection passes 3 fault injections in CI.
- JSI HostObject round-trip: RN → Rust → RN ≤ 5 ms p95 warm cache.
- Schema supports a Federation with 2 Cohorts and 5 athletes via API; cross-org read denied for Solo.
- ConsentRecord captures separable purposes; withdrawal triggers a row-level access denial in audit log within 60 s.
- Apple/Google engagement letters logged with response tracking.

---

#### SPRINT 5 — Capture End-to-End, WatermelonDB Sync, Calibration, First Egypt Capture

**Goal:** A user can complete a session on real Hero 13. Files land in backend storage. Offline-first sync engine works. DPIA signed before first Egypt capture.

**EPIC 5.1 Recording Lifecycle in Mobile (TRACK-MOBILE + TRACK-CORE)**
- [P0] Pre-session connection screen + retry/recovery copy.
- [P0] Session configuration screen (discipline, station, notes, athlete selection from Cohort).
- [P0] Active recording screen (no live feed yet — that's S7).
- [P0] End-session triggers download from Hero 13.
- [P0] Pause/resume with dual-track state in core.

**EPIC 5.2 WatermelonDB Offline-First Sync Engine (TRACK-MOBILE + TRACK-BACKEND)** *(pulled from V1 Sprint 12 — per Mobile review #3)*
- [P0] **WatermelonDB integrated** as local store; reactive queries to UI.
- [P0] **Bidirectional sync engine** (last-write-wins with vector-clock conflict markers).
- [P0] Background upload (continues when app backgrounded).
- [P0] Conflict-resolution UI for the rare cases that escape automerge.
- [P0] **Queue-and-resume** for cloud upload when connectivity returns.
- [P0] Online/offline state indicators in every screen.

**EPIC 5.3 File Ingestion Pipeline (TRACK-MOBILE + TRACK-BACKEND)**
- [P0] Files transfer Hero 13 → phone over Wi-Fi 5 GHz (or USB-C if federation rig).
- [P0] Phone → backend object storage with chunked resumable upload.
- [P0] Backend records Session + Recording entities with `camera_clock_offset_ms`.

**EPIC 5.4 Calibration Flow (TRACK-MOBILE + TRACK-ML)** *(per Embedded review #5)*
- [P0] **ChArUco board-based calibration** (12×9 board, OpenCV `calibrateCamera` + `solvePnP`).
- [P0] Calibration UI flow with reprojection-error reporting.
- [P0] Per-session calibration persisted; threshold for re-calibration documented.
- [P1] Bundle adjustment scoped (Ceres) for V1.5 multi-camera.

**EPIC 5.5 First Real Data Collection at Egypt (TRACK-DATA)** *(gated by DPIA)*
- [P0] **DPIA signed by counsel and DPO before any capture begins.** *Per Compliance review (#7).*
- [P0] **PDPC license on file or interim authorization in writing.**
- [P0] First Egypt training session captured with parental consent on file for any minors.
- [P0] Raw video uploaded under residency policy (EU region).
- [P0] Franco's first annotation pass on a 20-shot sample.
- [P1] Annotation taxonomy refined.

**[GATE] Sprint 5 measurable criteria:**
- DPIA signed; cross-border permit on file or stayed pending counsel-approved interim cover.
- A user can connect, record, end, and the session lands in backend storage; CI replays a golden session and asserts on schema completeness.
- WatermelonDB sync passes a 10-minute disconnected session, then uploads on reconnect with no data loss in CI test.
- ChArUco calibration produces ≤ 3 mm reprojection error at 5 m baseline on the office rig.
- ≥ 1 real Egypt session captured and stored with full consent records linked.

---

#### SPRINT 6 — Audio Backbone, Pose Backbone, Annotator #2, App-Store TestFlight

**Goal:** Audio shot detection production-grade. Pose backbone proven on shooting footage. Annotator #2 hired and contributing. App-Store TestFlight build live for internal testers. Wizard-of-Oz LLM coaching notes begin.

**EPIC 6.1 Audio Shot Detection (TRACK-ML)** *(per AI review #1)*
- [P0] YAMNet/PANNs-style CNN trained on initial Egypt + recreational data.
- [P0] Inference integrated on mobile (TFLite/ONNX).
- [P0] Inter-shot interval analysis; multi-shooter caveat documented.
- [P0] **Foam windscreen as hardware SKU**; wind-noise filter in pipeline. *Per Embedded review (#5).*
- [P1] **TDOA-ready audio capture** (per-camera channel layout) wired even though microphone array hardware lands V1.5.

**EPIC 6.2 Pose and Gun Tracking (TRACK-ML)**
- [P0] **RTMPose-x integrated**; stable keypoints on shooting footage at oblique stations.
- [P0] **MMPose Wholebody** added for hand and face keypoints.
- [P0] **SAM2 segmentation** prototyped for shooter+gun unit through occlusion.
- [P0] Custom YOLO for shotgun barrel detection (training initiated).
- [P1] Barrel angle estimation prototype.

**EPIC 6.3 Per-Shot Feature Extraction (TRACK-ML)**
- [P0] Pipeline scaffolded; features defined (mount time, swing speed, head stability, follow-through duration, barrel-to-target angle).
- [P0] Audio-anchored ±2 s clip extraction implemented.
- [P0] Feature output validated against manual measurements on 20 shots.
- [P1] **VideoMAE-v2 pretraining run started** on raw shooting footage (no labels). *Per AI review (#1).*

**EPIC 6.4 Sample Post-Session Report Generation (TRACK-ML + TRACK-BACKEND)**
- [P0] Crude post-session report generated from a captured session.
- [P0] Hit/miss detection from audio alone.
- [P0] **Wizard-of-Oz LLM coaching notes**: Franco hand-writes structured outputs against a frozen JSON schema for 30 sessions; LLM is plumbed in S11 against these examples. *Per UX review (#8).*

**EPIC 6.5 Annotator #2 + Active Learning (TRACK-DATA)** *(per Sprint Prioritizer + AI reviews)*
- [P0] Second annotator-coach hired; trained on Franco's taxonomy.
- [P0] **Active learning queue live** (BALD or coreset selection); Franco only sees uncertain shots.
- [P0] CVAT customizations for shooting taxonomy completed.

**EPIC 6.6 App-Store TestFlight + Privacy Labels** *(per Sprint Prioritizer + Compliance reviews)*
- [P0] iOS TestFlight build distributed to internal testers.
- [P0] Android internal-track build live.
- [P0] **Privacy nutrition labels and Data Safety sections drafted** to actual data flows. *Per Compliance review (#7).*

**[GATE] Sprint 6 measurable criteria:**
- Audio shot detection: TPR ≥ 99% / FPR ≤ 1% on 200-shot held-out test set.
- RTMPose-x outperforms MediaPipe on shooting test set by ≥ 10 AP (whole-body).
- Annotator #2 produces ≥ 50 labelled shots; inter-annotator κ with Franco ≥ 0.65 reported.
- TestFlight build installs and runs end-to-end on iOS + Android internal testers.
- Wizard-of-Oz coaching notes for ≥ 10 sessions reviewed by Franco.

**[GATE: PHASE 1 COMPLETE]** All Phase 1 measurable gates passed; team ready for Phase 2 coach-flow build.

---

### PHASE 2 — COACH OS, LIVE FEED, IMU

#### SPRINT 7 — Live Preview, Coach Web Foundation, Hire Closure

**Goal:** Live preview from Hero 13 running on Wi-Fi (Solo) and USB-C (federation). Coach web dashboard skeleton. Core engineering hiring closed.

**EPIC 7.1 Live Preview Stream (TRACK-CORE + TRACK-MOBILE)**
- [P0] Wi-Fi UDP MPEG-TS H.264 ingest in Rust; decoded to native module.
- [P0] **USB-C UVC live preview** at 1080p, ~200–400 ms latency, federation tier. *Per Embedded review (#5).*
- [P0] Frames bridged via JSI to RN render layer with shared-buffer zero-copy.
- [P0] **Performance budget validated**: live preview sustains ≥ 24 fps without dropping below 22 fps over 10 minutes; battery drain measured.

**EPIC 7.2 Pose Overlay (TRACK-MOBILE + TRACK-ML)**
- [P0] RTMPose-x overlay drawn on live preview (Reanimated-driven for jank-free rendering).
- [P0] Performance budget: < 1% frame drops at 30 fps overlay.

**EPIC 7.3 Coach Web Dashboard Skeleton (TRACK-WEB)** *(pulled forward from V1 Sprint 13)*
- [P0] React + Vite + TypeScript scaffolded.
- [P0] Auth flow (shared backend).
- [P0] Org / Cohort / Athlete browse views (read-only).
- [P0] Live-session viewer skeleton with multi-feed grid.

**EPIC 7.4 Core Hiring Closed** *(per Sprint Prioritizer review #8)*
- [P0] Mobile Engineer (native modules) onboarded.
- [P0] ML/CV Specialist (3D, IMU fusion) onboarded.
- [P0] Web Engineer onboarded.

**[GATE] Sprint 7 measurable criteria:**
- Live preview: Wi-Fi p50 ≤ 2.0 s end-to-end glass-to-glass; USB-C p50 ≤ 600 ms.
- Pose overlay sustains 24 fps with < 1% dropped frames over 10 minutes.
- Web dashboard authenticated, lists Cohorts and Athletes, opens a live-session skeleton.
- Core engineering team at full V1 strength.

---

#### SPRINT 8 — Per-Shot Detection, Feed Plumbing, RTMPose-x in Production

**Goal:** Per-shot events surfaced to live feed UI in near-real-time. RTMPose-x replaces all MediaPipe in production. ≥ 500 shots labelled.

**EPIC 8.1 Live Audio Shot Detection in Session (TRACK-ML + TRACK-MOBILE)**
- [P0] Audio capture from camera mic during live session at 48 kHz mono PCM (no AAC re-encode latency).
- [P0] Continuous shot detection during session.
- [P0] Detected shots fire events to UI within ≤ 500 ms of audio impulse.

**EPIC 8.2 Shot Event Pipeline (TRACK-MOBILE + TRACK-BACKEND)**
- [P0] Shot event schema standardized; WatermelonDB local store + sync.
- [P0] Reconciliation if connection drops mid-session; orphan-session recovery.

**EPIC 8.3 Live Feed Panel UI (TRACK-MOBILE)**
- [P0] Feed panel alongside video panel (single-screen layout).
- [P0] Feed entry component with hit/miss/pattern visual hierarchy.
- [P0] **New-entry animation P95 frame-drop budget < 1%**; smooth scrolling at 60 fps with 500 entries (Reanimated). *Per Performance review (#10).*
- [P0] Tap entry → expand to shot detail.
- [P0] **Range Mode** variant of feed panel functional. *Per UX review (#8).*

**EPIC 8.4 Per-Shot Diagnostic Stub (TRACK-ML)**
- [P0] Stub diagnostic with primary diagnostic + confidence + abstention.
- [P0] Honest "cause unclear" path when calibrated confidence below class-specific threshold. *Per AI review (#1).*

**EPIC 8.5 Annotation Workflow Operationalized (TRACK-DATA)**
- [P0] Franco + annotator #2 weekly cadence.
- [P0] **≥ 500 shots labelled with double-annotation on 20% sample** (κ measured). *Per AI review (#1).*

**[GATE] Sprint 8 measurable criteria:**
- Audio-to-feed-entry: p50 ≤ 1.5 s, p95 ≤ 2.5 s. *Per Performance review (#10).*
- < 1% feed-render frame drops during a 100-shot session.
- RTMPose-x deployed everywhere; MediaPipe deleted from production paths.
- ≥ 500 labelled shots with κ ≥ 0.65 inter-annotator agreement.

---

#### SPRINT 9 — Hierarchical Diagnostic Head + Calibration

**Goal:** First real diagnostic classifications shown in feed entries with calibrated confidence and abstention.

**EPIC 9.1 Multi-Task Hierarchical Diagnostic Head (TRACK-ML)** *(per AI review #1)*
- [P0] Branches: head/eye, mount/stance, swing/lead, follow-through.
- [P0] Joint training on shared VideoMAE-v2 features with task-specific losses.
- [P0] Per-branch calibrated probabilities.
- [P0] **Meta-classifier** (or DAG-structured causal model: stance → mount → swing → break → outcome) on top.
- [P0] **Temperature scaling on held-out set; report ECE and Brier per class.**
- [P0] **Conformal prediction with 90% coverage guarantee.**
- [P0] **Per-class abstention thresholds** (head-lift ≠ stopped-gun calibration).

**EPIC 9.2 Diagnostic Integration in Live Feed (TRACK-MOBILE + TRACK-ML)**
- [P0] Inference integrated into live shot pipeline.
- [P0] Diagnostic line text generated.
- [P0] Calibrated low-confidence → "cause unclear" route.
- [P1] Coach-mode vs athlete-mode tone variations.

**EPIC 9.3 Outcome Detection (TRACK-ML)**
- [P0] Hit/miss from audio + visual signal fusion.
- [P0] Manual override path in UI.
- [P0] Outcome accuracy measured against double-annotated labels.

**EPIC 9.4 Tap-to-Review (TRACK-MOBILE)**
- [P0] Tap entry → playback in video panel at 0.25× / 0.5×.
- [P0] Annotations drawn on playback (head movement, swing path).
- [P1] Frame-by-frame stepping.

**EPIC 9.5 Backend Aggregation Hooks (TRACK-BACKEND)**
- [P0] Session-end event triggers post-session pipeline.
- [P0] Shot data persisted with full context including calibration metadata.

**[GATE] Sprint 9 measurable criteria:**
- Diagnostic per-class macro-F1 ≥ 0.7 on held-out double-annotated test set with **denominator declared**: 500-shot Egypt-mixed-lighting test set, stratified per station and per body-type. *Per AI review (#1).*
- ECE ≤ 0.05 per branch; Brier scores reported.
- Conformal prediction sets cover ≥ 90% of true labels at p ≤ 0.1.
- Outcome detection ≥ 90% accuracy (good lighting) vs double-annotated labels.

**[STOP-THE-LINE] If diagnostic per-class macro-F1 < 0.6 at S9 close, halt feature work; reallocate ML + annotation capacity. *Per Sprint Prioritizer review (#9).***

---

#### SPRINT 10 — Live Feed v1, IMU Integration, Connection Robustness

**Goal:** Live coaching feed feels v1. IMU integrated as P1. Reconnection rock-solid.

**EPIC 10.1 Pattern Detection in Session (TRACK-ML)**
- [P0] Rolling-window pattern detection.
- [P0] Pattern definitions (3+ consecutive same diagnostic, station-specific drift).
- [P0] Significance thresholds tuned to per-class calibration.

**EPIC 10.2 Feed Polish (TRACK-MOBILE)**
- [P0] Visual hierarchy refined.
- [P0] Tone modes (coach, athlete, silent).
- [P0] Filter controls (all, misses only, flagged only).
- [P0] Range Mode polish.

**EPIC 10.3 IMU Integration P1 (TRACK-CORE + TRACK-ML)** *(pulled from V2 → V1 per AI + Embedded reviews)*
- [P0] BLE protocol for stock-mounted IMU (MPU-6050 or BMI270 class).
- [P0] **Sensor fusion: audio shot timestamp ± IMU recoil signature** for sub-10 ms shot timing.
- [P0] Mount-jerk + swing-velocity features extracted from 200 Hz IMU.
- [P0] Feature flag — IMU off by default; opt-in flow with separate Art. 9 consent row.
- [P1] Stopped-gun / head-lift disambiguation experiment.

**EPIC 10.4 Pause/Resume + Voice Notes (TRACK-MOBILE)**
- [P0] Prominent pause/resume; auto-end after timeout.
- [P0] Voice note attached to shot or session.
- [P1] Voice transcription deferred (V1.5).

**EPIC 10.5 Connection Robustness (TRACK-CORE + TRACK-MOBILE)**
- [P0] Reconnection in real outdoor environments tested at Egypt.
- [P0] Camera continues recording during phone disconnects; reconcile after reconnection.
- [P0] Orphan session recovery flow.
- [P0] **BLE keepalive while Wi-Fi is down (mandatory, not P1).** *Per Embedded review (#5).*

**EPIC 10.6 Part-Time SRE Onboarded** *(per Sprint Prioritizer review #8)*
- [P0] On-call rotation defined; PagerDuty or Better Uptime configured.
- [P0] SLO dashboards live (Grafana on Prometheus).

**[GATE] Sprint 10 measurable criteria:**
- Live coaching feed: shot-to-feed-entry p50 ≤ 1.5 s, p95 ≤ 2.5 s on Wi-Fi; p50 ≤ 0.8 s on USB-C. *Per Performance review (#10).*
- Pattern surfacing precision ≥ 0.7 in real Egypt sessions vs Franco labels.
- Pause/resume passes 5 consecutive disconnect/reconnect cycles in field test.
- IMU shot timing within ± 10 ms of audio impulse on bench test.

---

#### SPRINT 11 — Post-Session Report MVP, LLM Live, Solo as Subset

**Goal:** Post-session report generates with all major sections. LLM coaching notes go from Wizard-of-Oz to live (with structured-output guards). Solo derived from Coach OS.

**EPIC 11.1 Post-Session Pipeline (TRACK-ML + TRACK-BACKEND)**
- [P0] Full-resolution analysis on recorded session files.
- [P0] Higher-accuracy server-side models (RTMPose-x + VideoMAE-v2 + ActionFormer).
- [P0] **ONNX/TensorRT INT8 quantization for server-side inference**, hardware spec'd. *Per AI review (#1).*
- [P0] Multi-pass: in-session baseline → anomaly detection → diagnostic.
- [P0] **Pipeline runs within p50 ≤ 90 s, p95 ≤ 150 s, hard cap 180 s with degraded fallback** (skip 3D, drop VideoMAE pass, return audio + 2D + LLM only). *Per Performance review (#10).*

**EPIC 11.2 Report Sections (TRACK-MOBILE + TRACK-WEB + TRACK-BACKEND)**
- [P0] Headline summary; outcome-by-station heatmap; mechanical analysis charts; pattern findings; notable shots playlist (5–10).
- [P1] Recommended drills (basic).

**EPIC 11.3 LLM Coaching Notes Live (TRACK-ML + TRACK-BACKEND)** *(per AI review #1)*
- [P0] Ollama + DeepSeek (with lighter fallback) inference path.
- [P0] **JSON-schema constrained decoding** (Outlines/Guidance).
- [P0] **RAG over athlete's last 5 sessions** for style continuity.
- [P0] **Verifier pass**: second LLM call asks "do the cited features match the data?" — reject if not.
- [P0] LoRA-adapter scaffold for future fine-tune on Franco's edits.
- [P0] Generated notes reviewed by Franco; ≥ 80% pass without rewrite.

**EPIC 11.4 Report UI (TRACK-MOBILE + TRACK-WEB)**
- [P0] Report screens per design spec.
- [P0] Tab navigation; tap-to-view-shots from any section.
- [P0] Share clip from report.
- [P1] Export to PDF.

**EPIC 11.5 Solo Tier as Coach-OS Subset (TRACK-MOBILE)** *(per Architect + Sprint Prioritizer reviews)*
- [P0] Solo Org auto-provisioned for self-onboarded users; user holds athlete + coach roles in own Org.
- [P0] Feature flags collapse coach UI for Solo; data model unchanged.

**[GATE] Sprint 11 measurable criteria:**
- Post-session report p50 ≤ 90 s, p95 ≤ 150 s on 50-shot session.
- LLM verifier rejection rate < 10% on Franco's review of 30 reports; ≥ 80% accepted without rewrite.
- Solo flow completable end-to-end without dev assistance.

---

#### SPRINT 12 — Mobile Polish, Onboarding, Offline-First Hardening

**Goal:** Solo + coach apps feel production-grade for Egypt validation. (Note: WatermelonDB landed S5; this sprint hardens.)

**EPIC 12.1 Offline-First Hardening (TRACK-MOBILE + TRACK-BACKEND)**
- [P0] Sessions capture and analyze fully offline with on-device models.
- [P0] Conflict-resolution UX polished.
- [P0] Battery + thermal degradation ladder visible in UI.

**EPIC 12.2 Onboarding Flow Polish (TRACK-MOBILE)**
- [P0] First-time setup screens.
- [P0] Camera-pairing flow polished with clear error recovery.
- [P0] Welcome tutorial (skippable).
- [P0] Plan selection + payment integration.

**EPIC 12.3 Home + Sessions List (TRACK-MOBILE)**
- [P0] Home per spec.
- [P0] Sessions list with filtering and search.
- [P0] Last-session card, performance strip, current focus card.

**EPIC 12.4 Camera Management (TRACK-MOBILE)**
- [P0] Paired cameras list + management.
- [P0] Add new camera flow.
- [P0] **Firmware-update detection with matrix-aware refusal.** *Per Embedded review (#5).*

**EPIC 12.5 Settings + Preferences (TRACK-MOBILE)**
- [P0] Account, subscription, notification, display, overlay preferences.
- [P0] Consent management screen — view all granted purposes; withdraw any.

**[GATE] Sprint 12 measurable criteria:**
- Solo app passes internal dogfooding: 5 full sessions per team member with zero dev intervention.
- Offline mode: full session capture + analysis + later sync, zero data loss in CI replay.
- Onboarding completable end-to-end without dev assistance on iOS + Android.
- Battery drain: **< 18%/hr iPhone 13; < 22%/hr Pixel 6a** on 60-min session at room temp. *Per Performance review (#10).*

**[GATE: PHASE 2 COMPLETE]** Coach OS works; Solo derived; ready for polish + analytics.

---

### PHASE 3 — POLISH, ANALYTICS, COMPLIANCE CONTROLS

#### SPRINT 13 — Coach Dashboard Production, Coach Annotations

**Goal:** Coach dashboard production-grade for multi-athlete operations. (Schema landed S4.)

**EPIC 13.1 Coach Dashboard Production (TRACK-WEB + TRACK-BACKEND)**
- [P0] Multi-coach support per Org with permissions enforced.
- [P0] Athlete roster: list, search, filter; profile detail; performance overview.
- [P0] Coach-operated session: pick athlete, start on club camera, run live view.
- [P0] Athlete switching for back-to-back sessions.

**EPIC 13.2 Coach Annotations (TRACK-WEB + TRACK-BACKEND)**
- [P0] Annotations on shots and sessions.
- [P0] Visibility scopes: private, share with athlete, share with club.
- [P0] Annotations appear in athlete report when shared.

**[GATE] Sprint 13 measurable criteria:**
- Coach can register 10 athletes and run 5 sessions in one day; coach action latency ≤ 200 ms p95 on dashboard.
- Annotation visibility scope enforced — verified by automated security test (athlete cannot read coach-private rows).

---

#### SPRINT 14 — Longitudinal Analytics + SOC 2 Type I Controls

**Goal:** Cross-session pattern detection + trend tracking. SOC 2 Type I controls implementation kickoff.

**EPIC 14.1 Longitudinal Pipeline (TRACK-ML + TRACK-BACKEND)** *(per AI review #1)*
- [P0] Per-athlete baseline maintained.
- [P0] **Bayesian structural time-series** (or per-athlete Transformer with athlete-ID embedding) replaces rolling-window pattern detection.
- [P0] Regime change vs noise distinguished with calibrated uncertainty.
- [P0] Cross-session pattern detection.

**EPIC 14.2 Comparison-to-History (TRACK-MOBILE + TRACK-WEB)**
- [P0] "Compared to last 10 sessions" sections.
- [P0] Baseline measurements alongside current.
- [P0] Charts over time.

**EPIC 14.3 Performance Dashboard (TRACK-MOBILE + TRACK-WEB)**
- [P0] Athlete-facing performance dashboard.
- [P0] Hit-rate trends, mechanical-variable trends.
- [P0] Filter by discipline, date range, equipment.

**EPIC 14.4 Pre-Competition Readiness Indicator (TRACK-ML)**
- [P1] Readiness score from recent training; surfaces on home.

**EPIC 14.5 SOC 2 Type I Controls Implementation Kickoff** *(per Compliance review #7)*
- [P0] **SOC 2 auditor engaged** (Tier-1 firm).
- [P0] Controls baseline implemented: change management, access reviews, vendor management, incident response runbooks.
- [P0] **DPA templates signed with Railway, AWS, Sentry, Apple, Google, Ollama hosting** by S14 close. *Per Compliance review (#7).*
- [P0] ISO 27001 + 27701 control mapping started.

**[GATE] Sprint 14 measurable criteria:**
- Longitudinal patterns visible after ≥ 10 sessions per athlete on Egypt cohort.
- SOC 2 control evidence-collection live; ≥ 70% of CC controls operating.
- All third-party DPAs signed; Art. 30 RoPA up to date.

---

#### SPRINT 15 — Drill Library, Lesson Plans, Cross-Discipline Scaffolding

**Goal:** Drill library browsable. Coaches build lesson plans. Trap + sporting clays data-model scaffolding.

**EPIC 15.1 Drill Library (TRACK-MOBILE + TRACK-WEB + TRACK-BACKEND)**
- [P0] Drill data model + content management.
- [P0] Initial drill content (Franco-curated, 30+ drills).
- [P0] Browse + search on mobile + web.
- [P0] Drill detail view with video.

**EPIC 15.2 Recommended Drills (TRACK-ML)**
- [P0] Recommendation algorithm grounded in detected patterns.
- [P0] Surfaces in post-session reports.
- [P1] Save / dismiss.

**EPIC 15.3 Lesson Plan Builder (TRACK-WEB)**
- [P0] Coach builds structured session ahead of time.
- [P0] Templates savable + reusable.

**EPIC 15.4 Drill Assignments (TRACK-WEB + TRACK-MOBILE)**
- [P0] Coach assigns drill to athlete with linked Solo account.
- [P0] Assignment surfaces on athlete home.

**EPIC 15.5 Cross-Discipline Scaffolding** *(per Trend review #6)*
- [P0] **Trap + sporting clays** taxonomy + data-model scaffolding (no ML release; structure-only so V1.5 ML is additive).
- [P0] Discipline-aware feature flags throughout pipeline.

**[GATE] Sprint 15 measurable criteria:**
- ≥ 30 drills live with quality content.
- Recommendation algorithm: relevance ≥ 0.7 (Franco-rated) on 50 generated recommendations.
- Cross-discipline schema migration shipped; trap+sporting taxonomies in CVAT.

---

#### SPRINT 16 — QR Cross-Tier Check-in

**Goal:** Solo users check in at AIMVISION-enabled clubs via QR. Personal reports derived from coach session.

**EPIC 16.1 QR Generation in Solo (TRACK-MOBILE)**
- [P0] Check-in screen.
- [P0] Short-lived scoped token; expiry countdown.
- [P0] Cancel flow.

**EPIC 16.2 QR Scanning in Club Dashboard (TRACK-WEB)**
- [P0] Camera-based QR scan in coach dashboard.
- [P0] Token validation against backend.
- [P0] Athlete confirmation with photo.
- [P0] Add to session queue.

**EPIC 16.3 Token Backend Service (TRACK-BACKEND)** *(see `docs/security/qr-checkin-token-spec.md`)*
- [P0] Scoped-token issuance + validation.
- [P0] Single-use enforcement.
- [P0] Time-limited expiry.
- [P0] **Audit logging of every check-in** linked to ConsentRecord.

**EPIC 16.4 Derived Personal Reports (TRACK-BACKEND + TRACK-ML)**
- [P0] Session attribution model with `checkin_token` reference.
- [P0] Personal-report derivation: only this user's shots.
- [P0] Visibility-scope enforcement.
- [P0] Sync to Solo user's account.

**EPIC 16.5 Solo App: View Club Sessions (TRACK-MOBILE)**
- [P0] Notification when club-session report ready.
- [P0] Club-session report rendering (same UI as solo, scoped data).

**[GATE] Sprint 16 measurable criteria:**
- E2E check-in works at Egypt facility with ≥ 5 successful check-ins.
- Solo user receives personal report within ≤ p95 150 s of session end.
- **Automated security test confirms other athletes' shots excluded from a Solo user's report**.

---

#### SPRINT 17 — Federation Admin, Audit GA, Per-Athlete LoRA

**Goal:** Federation-admin features production-grade. Audit logging GA. Per-athlete LoRA personalization landing.

**EPIC 17.1 Federation Admin Dashboard (TRACK-WEB)**
- [P0] Multi-program overview (national team, junior, etc.).
- [P0] Cohort analytics across athletes (consent-aware).
- [P0] Talent-identification view.
- [P1] Federation-wide pattern mining.

**EPIC 17.2 Audit Logging GA (TRACK-WEB + TRACK-BACKEND)** *(per Compliance review #7)*
- [P0] All sensitive operations covered (auth, consent, data access, model retrain, deletion).
- [P0] Audit-log viewer in admin dashboard.
- [P0] Data export for compliance reporting.
- [P0] Retention policy configuration UI.
- [P0] **Right-to-erasure cascade designed and shipped** — S3, training datasets, audit logs, backups, model-shard deletion path documented; documented Art. 17(3)(b) exemption argument with counsel for in-weight residue. *Per Compliance review (#7).*

**EPIC 17.3 Per-Athlete LoRA Personalization (TRACK-ML)** *(per AI review #1)*
- [P0] LoRA adapters per athlete after ~200 shots.
- [P0] Personalized diagnostic-head fine-tune; gated by athlete consent for ML training.
- [P0] Per-athlete model isolation simplifies erasure.

**[GATE] Sprint 17 measurable criteria:**
- Federation admin runs cohort analytics across ≥ 20 athletes with consent-scope enforcement verified by automated test.
- Audit log captures 100% of declared sensitive events; retention policy configurable per Org.
- Right-to-erasure cascade demonstrated end-to-end on a test account.
- Per-athlete LoRA improves macro-F1 by ≥ 0.05 vs base model on held-out personal data.

**(SCOPE-CUT NOTE)** On-prem federation deployment validation deferred to V1.5 per Sprint Prioritizer review (#9). Architecture remains portable; no V1 deployment required.

---

#### SPRINT 18 — RTL, Accessibility GA, Validity Study Protocol Locked

**Goal:** App passes accessibility audit. Arabic + RTL production-grade. Validity-study protocol locked and IRB pre-engagement.

**EPIC 18.1 Localization GA (TRACK-MOBILE + TRACK-WEB)**
- [P0] All strings extracted; English baseline complete.
- [P0] **Arabic translations integrated; RTL layouts verified on every screen.**
- [P0] **Spanish dropped from V1** (deferred V1.5). *Per Sprint Prioritizer review (#9).*

**EPIC 18.2 RTL Layout (TRACK-MOBILE + TRACK-WEB)**
- [P0] All screens render correctly in RTL.
- [P0] Icons + directional elements mirror.
- [P0] Bidi text input handling.

**EPIC 18.3 Accessibility GA (TRACK-MOBILE + TRACK-WEB)**
- [P0] WCAG 2.1 AA color contrast.
- [P0] Screen-reader labels on every interactive element.
- [P0] Dynamic type support.
- [P1] Keyboard navigation on web.
- [P1] Caption support for video.

**EPIC 18.4 Empty / Error / Loading States (TRACK-MOBILE + TRACK-WEB)**
- [P0] Designed empty states for every list.
- [P0] Designed error states with clear recovery actions.
- [P0] Loading states for ops > 2 s.
- [P0] Offline mode states.

**EPIC 18.5 Validity Study Protocol Locked** *(per AI + Sprint Prioritizer reviews)*
- [P0] **Validity-study protocol locked** with sport-science partner; IRB pre-engagement complete.
- [P0] Inter-annotator agreement design with ≥ 2 expert coaches in addition to Franco.
- [P0] Stratified eval plan: per-station, per-discipline, per-lighting, per-body-type, per-skin-tone.

**[GATE] Sprint 18 measurable criteria:**
- App passes external accessibility audit.
- Arabic + RTL rendered correctly on 100% of audited screens; bidi text input passes test corpus.
- Validity-study protocol signed by partner; IRB submission ready.

**[GATE: PHASE 3 COMPLETE]** Feature scope locked; ready for validation.

---

### PHASE 4 — VALIDATION

#### SPRINT 19 — Egypt Validation, SOC 2 Type II Window Opens

**Goal:** Egypt national team uses AIMVISION daily. SOC 2 Type II observation window opens. Validity-study data collection begins.

**EPIC 19.1 Egypt Deployment (TRACK-ALL)**
- [P0] Full system deployed; daily usage begins.
- [P0] On-site setup + training session with athletes + coaches.
- [P0] **Single-camera primary** for V1 daily use; secondary camera for validation video only.

**EPIC 19.2 Validation Metrics Collection (TRACK-ML + TRACK-DATA)**
- [P0] Accuracy across all ML components stratified per slice.
- [P0] **Diagnostic agreement with Franco + ≥ 2 other expert coaches; report Cohen's κ as the ceiling.** *Per AI review (#1).*
- [P0] Coach overrides tracked → model improvement feedback.
- [P0] Structured + unstructured user feedback channels.

**EPIC 19.3 Bug Triage and Hotfix Loop (TRACK-ALL)**
- [P0] Bug-tracking + triage process.
- [P0] Daily hotfix releases as needed (EAS Update).
- [P0] Hotfix path documented.

**EPIC 19.4 Performance Profiling (TRACK-ML + TRACK-MOBILE)** *(per Performance review #4)*
- [P0] Live coaching feed latency in real conditions.
- [P0] Post-session report generation time.
- [P0] **Battery drain on iPhone 13 + Pixel 6a measured; thermal degradation ladder validated for 60 min @ 35 °C.**
- [P0] Camera thermal behavior in Egyptian climate.

**EPIC 19.5 SOC 2 Type II Window Opens** *(per Compliance review #7)*
- [P0] Observation window starts; auditor engaged for 6-month run-up to S24/post-launch.

**EPIC 19.6 Validity Study Collection Begins** *(per AI review #1)*
- [P0] IRB-approved data collection at Egypt under research protocol.

**[GATE] Sprint 19 measurable criteria:**
- ≥ 5 full national team training sessions on the system.
- Critical issues triaged with documented dispositions.
- **Live feed: P95 shot-to-feed-entry < 2.5 s across 5 consecutive Egypt sessions; < 1% feed-render frame drops measured in production telemetry.** *Per Sprint Prioritizer review (#9) + Performance review (#10).*

---

#### SPRINT 20 — Accuracy Tuning + Hardening

**Goal:** ML accuracy meets V1 thresholds. System robust in real conditions.

**EPIC 20.1 Model Retraining with Egypt Data (TRACK-ML)**
- [P0] All models retrained with collected data.
- [P0] **Diagnostic per-class macro-F1 ≥ 0.75 on stratified Egypt eval; calibration ECE ≤ 0.04.**
- [P0] **Outcome detection ≥ 95% in good lighting; ≥ 88% in harsh sun** (declared denominators per slice).
- [P0] Pattern-detection precision validated.

**EPIC 20.2 Edge Case Handling (TRACK-ALL)**
- [P0] Multi-shooter audio interference mitigation (TDOA prep).
- [P0] Bright sunlight handling.
- [P0] Camera-overheating graceful behavior with thermal degradation ladder.
- [P0] Network connectivity edge cases.

**EPIC 20.3 Performance Optimization (TRACK-MOBILE + TRACK-ML)** *(per Performance review #4)*
- [P0] **Live coaching feed: p50 ≤ 2.5 s / p95 ≤ 4 s on Wi-Fi; p50 ≤ 1.2 s on USB-C.**
- [P0] **Post-session report: p50 ≤ 90 s, p95 ≤ 150 s, hard cap 180 s with degraded fallback.**
- [P0] **Battery drain optimized: < 18%/hr iPhone 13; < 22%/hr Pixel 6a.**
- [P0] **Sustained 60 min @ 35 °C with thermal degradation ladder** (drop overlays → drop in-session classification → audio-only) in that order.
- [P1] Older device support validated (lite model variants).

**EPIC 20.4 Coach Workflow Refinement (TRACK-WEB + TRACK-MOBILE)**
- [P0] Coach feedback into UI changes.
- [P0] Frequently used coach actions optimized.
- [P0] Athlete-switching speed optimized for back-to-back sessions.

**[GATE] Sprint 20 measurable criteria:**
- All accuracy thresholds met or exceeded with declared denominators.
- All performance SLOs hit in production telemetry across 10 consecutive Egypt sessions.
- Coach-workflow rated ≥ 4.0/5 by Egypt coaching staff.

---

#### SPRINT 21 — Beta Program + Penetration Test

**Goal:** Closed beta beyond Egypt. Independent pen test passes.

**EPIC 21.1 Closed Beta Recruitment (BUSINESS)**
- [P0] 30–50 closed beta Solo users.
- [P0] 2–3 additional clubs for Club tier beta — **including ≥ 1 Western club** as the secondary design partner. *Per Trend review (#2).*
- [P0] Beta agreement + feedback channel.

**EPIC 21.2 Beta Onboarding (TRACK-MOBILE + TRACK-WEB)**
- [P0] Invitation-code beta access flow.
- [P0] Beta-specific feedback widgets.

**EPIC 21.3 Beta Issue Resolution (TRACK-ALL)**
- [P0] Daily triage; critical issues resolved within sprint; pattern issues tracked.

**EPIC 21.4 Penetration Test** *(per Compliance review #7)*
- [P0] **External pen test by CREST/OSCP-credentialed firm.**
- [P0] All criticals + highs remediated before close.
- [P0] Pen-test report archived for federation procurement.

**EPIC 21.5 Validity Study Data Collection (continues)**
- [P0] Continue collection per IRB protocol.

**[GATE] Sprint 21 measurable criteria:**
- Beta users completing sessions independently; ≥ 70% complete a session within first 48 h.
- NPS ≥ 30 at sprint close.
- Pen test: zero unresolved critical or high findings.
- All criticals from beta resolved.

**[GATE: PHASE 4 COMPLETE]** Validated product; ready for launch prep.

---

### PHASE 5 — LAUNCH

#### SPRINT 22 — Pre-Launch Polish, Bug Bounty, Marketing Site

**Goal:** Marketing surface live. Bug bounty + responsible-disclosure published. App Store submissions in.

**EPIC 22.1 Marketing Website (BUSINESS + TRACK-WEB)**
- [P0] aimvision.app marketing site live.
- [P0] Founder story (Franco) prominent.
- [P0] Product overview by tier.
- [P0] Pricing page.
- [P0] Egypt case study published — **adults only on camera; minors blurred or excluded; signed publicity-rights releases archived.** *Per Compliance review (#7).*
- [P0] Waitlist → launch announcement.
- [P0] SEO baseline.

**EPIC 22.2 App Store Submission (TRACK-MOBILE)**
- [P0] iOS metadata, screenshots, video preview.
- [P0] Google Play metadata, screenshots, video preview.
- [P0] **Apple/Google review-guidelines compliance verified** with the engagement context built since S6.
- [P0] Initial submissions made.
- [P0] Privacy nutrition labels and Data Safety sections final.

**EPIC 22.3 Customer Support (BUSINESS)**
- [P0] Help center / KB.
- [P0] In-app chat or email support.
- [P0] Support ticket triage process.
- [P0] FAQ.

**EPIC 22.4 Subscription + Payment Hardening (TRACK-MOBILE + TRACK-BACKEND)**
- [P0] Apple IAP tested.
- [P0] Google Play Billing tested.
- [P0] Stripe web checkout for Club tier.
- [P0] Refund + cancellation flows.

**EPIC 22.5 Analytics + Monitoring GA (TRACK-BACKEND)**
- [P0] Product analytics events instrumented (PostHog or Amplitude).
- [P0] Sentry production project; alerting on critical paths.
- [P0] Performance monitoring (response times, ML inference times, SLO dashboards).
- [P0] On-call rotation finalized.

**EPIC 22.6 Bug Bounty + Responsible Disclosure** *(per Compliance review #7, DevOps review #10)*
- [P0] **Public security.txt + responsible-disclosure policy published.**
- [P0] Bug-bounty program launched (HackerOne or open) with scoped scope.

**[GATE] Sprint 22 measurable criteria:**
- Marketing site live with full content; minor-protection rules audited on every asset.
- Apps submitted to both stores.
- Bug-bounty live; security.txt resolves at HTTPS root.

---

#### SPRINT 23 — Launch Readiness

**Goal:** All systems go. Apps approved.

**EPIC 23.1 App Store Approval Loop (TRACK-MOBILE)**
- [P0] Address review feedback.
- [P0] Re-submission if needed.
- [P0] Final approved builds in stores.

**EPIC 23.2 Press + PR Prep (BUSINESS)**
- [P0] Press release (founder story).
- [P0] Sports-tech publication outreach.
- [P0] Shooting-sports media outreach.
- [P0] Social media presence.
- [P1] Embargo coordination.

**EPIC 23.3 Federation Outreach Prep (BUSINESS)**
- [P0] List of 30–40 priority ISSF federations.
- [P0] Outreach materials.
- [P0] Initial introductions begun via Franco's network.
- [P1] Demo environment ready.

**EPIC 23.4 Final Bug Fixes + Polish (TRACK-ALL)**
- [P0] Final regression testing on golden sessions.
- [P0] Critical issues resolved.
- [P0] Capacity scaling pre-warmed.

**EPIC 23.5 Launch Operations Plan (BUSINESS + TRACK-ALL)**
- [P0] Launch-day runbook.
- [P0] On-call rotation scheduled.
- [P0] Communication plan.

**[GATE] Sprint 23 measurable criteria:**
- Apps approved and live in both stores.
- Press materials ready.
- Launch-day runbook signed off by full team.

---

#### SPRINT 24 — Public Launch + SOC 2 Type I Report

**Goal:** Public launch of Solo tier. Egypt as showcase. SOC 2 Type I report delivered.

**EPIC 24.1 Launch Announcement (BUSINESS)**
- [P0] Public launch announcement.
- [P0] Press release distributed.
- [P0] Social media campaign.
- [P0] Founder posts + interviews.

**EPIC 24.2 Launch Day Operations (TRACK-ALL)**
- [P0] On-call team monitoring.
- [P0] Rapid response to critical issues.
- [P0] Hourly internal status updates.
- [P0] Capacity scaling triggered as needed.

**EPIC 24.3 Early User Onboarding (BUSINESS)**
- [P0] Welcome email series.
- [P0] In-app guidance for first session.
- [P0] Conversion monitoring (signup → first session → subscription).

**EPIC 24.4 Federation Engagement Begins (BUSINESS)**
- [P0] Active outreach to priority federations.
- [P0] Demo calls scheduled.
- [P0] Egypt + secondary-Western design-partner case studies leveraged.
- [P1] First federation pilot agreements in negotiation.

**EPIC 24.5 SOC 2 Type I Report Delivered** *(per Compliance review #7)*
- [P0] **SOC 2 Type I report issued by auditor**; archived for federation procurement.

**EPIC 24.6 Post-Launch Retrospective (TEAM)**
- [P0] Launch retro.
- [P0] Top 10 issues prioritized for V1.1.
- [P0] V1.5 roadmap confirmed from usage data.

**[GATE] Sprint 24 measurable criteria:**
- V1 publicly launched in both app stores.
- ≥ 100 paying subscribers.
- ≥ 3 federation conversations active.
- SOC 2 Type I report delivered and on procurement portal.

**[GATE: V1 LAUNCH COMPLETE]** AIMVISION V1 is in market. Transitioning to growth + V1.5 planning. SOC 2 Type II observation continues.

---

## 5. Phase gate criteria — measurable

All gates were rewritten as measurable objectives per Sprint Prioritizer review (#9) and Performance Benchmarker review (#10).

### Phase 0 gate (after Sprint 2)
- DPO contract executed; PDPC license application receipted; both counsels engaged; DPIA scope agreed in writing.
- Architecture doc + threat model + data classification table merged; signed by CTO + DPO + Founder.
- Stack commitments locked: RN New Arch (JSI/Fabric/Hermes), Python+FastAPI, Rust+UniFFI, PyTorch/MMPose, GoPro Labs (federation tier), USB-C P0 (federation tier).
- ≥ 2 engineers contributing (≥ 5 merged PRs each).
- Pinned firmware matrix + startup-check skeleton in repo.

### Phase 1 gate (after Sprint 6)
- Real Hero 13 connects + records on pinned firmware over Wi-Fi + USB-C; force-unpair recovery passes.
- Mobile app shell with age gate, parental consent, RTL, a11y, Sentry, feature flags, EAS OTA, PrivacyInfo, battery+thermal telemetry, audit logging.
- WatermelonDB sync passes 10-min disconnected-session test in CI without data loss.
- Audio shot detection: TPR ≥ 99% / FPR ≤ 1% on 200-shot held-out test set.
- RTMPose-x outperforms MediaPipe on shooting test set by ≥ 10 AP (whole-body).
- ≥ 1 Egypt session captured under signed DPIA + on-file PDPC license; ≥ 50 shots labelled with Franco/annotator-#2 κ ≥ 0.65.
- TestFlight + Android internal-track builds installable.

### Phase 2 gate (after Sprint 12)
- Live coaching feed: shot-to-feed-entry p50 ≤ 1.5 s, p95 ≤ 2.5 s on Wi-Fi; p50 ≤ 0.8 s on USB-C; < 1% feed-render frame drops over 100-shot session.
- Diagnostic per-class macro-F1 ≥ 0.7 on declared 500-shot stratified Egypt test set; ECE ≤ 0.05; conformal coverage ≥ 90%.
- Post-session report: p50 ≤ 90 s, p95 ≤ 150 s, hard cap 180 s on 50-shot session.
- LLM coaching notes: ≥ 80% Franco-acceptance without rewrite; verifier rejection rate < 10%.
- Solo derives from coach OS; full session flow offline + later sync, zero data loss in CI replay.
- Battery drain < 18%/hr iPhone 13 / < 22%/hr Pixel 6a; sustained 60 min @ 35 °C with documented degradation ladder.
- IMU shot timing within ± 10 ms of audio impulse on bench test.

### Phase 3 gate (after Sprint 18)
- Coach dashboard supports multi-athlete workflows at coach-action latency p95 ≤ 200 ms.
- Longitudinal analytics surface meaningful patterns after ≥ 10 sessions per athlete on Egypt cohort.
- ≥ 30 quality drills; recommendation relevance ≥ 0.7 (Franco-rated, n=50).
- QR check-in works end-to-end at Egypt with audit log and visibility-scope enforcement passing automated security tests.
- Federation admin runs cohort analytics across ≥ 20 athletes with consent-scope enforcement verified.
- Audit logging GA; right-to-erasure cascade demonstrated end-to-end.
- Per-athlete LoRA improves macro-F1 by ≥ 0.05 vs base model.
- App passes external accessibility audit; Arabic + RTL on 100% of audited screens.
- Validity-study protocol signed; IRB submission ready.
- SOC 2 Type I controls: ≥ 70% CC controls operating with evidence collection live; all third-party DPAs signed.

### Phase 4 gate (after Sprint 21)
- ≥ 5 full Egypt national team training sessions on the system; live feed P95 shot-to-feed-entry < 2.5 s across 5 consecutive sessions; < 1% feed-render frame drops in telemetry.
- Diagnostic per-class macro-F1 ≥ 0.75 on stratified Egypt eval; ECE ≤ 0.04; outcome detection ≥ 95% (good lighting), ≥ 88% (harsh sun).
- Closed beta users complete sessions independently; ≥ 70% complete a session within 48 h; NPS ≥ 30.
- Pen test: zero unresolved critical or high findings.
- SOC 2 Type II observation window open ≥ 2 sprints.

### Phase 5 gate (after Sprint 24)
- V1 publicly launched on both app stores.
- ≥ 100 paying subscribers.
- ≥ 3 federation conversations active.
- SOC 2 Type I report issued.
- Bug bounty live ≥ 1 sprint with documented intake process.

---

## 6. SLA targets

Honest, instrumented, and measured in production telemetry. *Per Performance Benchmarker review (#10) + Sprint Prioritizer review (#9).*

| Surface | p50 | p95 | Hard cap | Notes |
|---|---|---|---|---|
| Live coaching feed (Wi-Fi) | ≤ 2.5 s | ≤ 4 s | n/a | Reframed Solo path. Perceived-latency decoupling: animate "shot detected" tick at audio-impulse moment, fill diagnostic when ready. |
| Live coaching feed (USB-C) | ≤ 1.2 s | ≤ 2 s | n/a | Federation/Club coaching-grade path. |
| Post-session report | ≤ 90 s | ≤ 150 s | 180 s | Hard cap with degraded fallback (skip 3D, drop VideoMAE, audio + 2D + LLM only). |
| Coach-action dashboard | ≤ 100 ms | ≤ 200 ms | n/a | UI-ack only. |
| Battery drain (iPhone 13) | < 18%/hr | — | — | 60-min session at room temp. |
| Battery drain (Pixel 6a) | < 22%/hr | — | — | 60-min session at room temp. |
| Sustained capture | 60 min @ 35 °C | — | — | Thermal degradation ladder: drop overlays → drop in-session classification → audio-only. |
| Audio shot detection | ≥ 99% TPR | ≤ 1% FPR | — | On 200-shot held-out test set. |
| Diagnostic per-class macro-F1 | ≥ 0.75 | — | — | Stratified Egypt eval; ECE ≤ 0.04 per branch. |

---

## 7. Stop-the-line rules

Explicit phase-rollback triggers. *Per Sprint Prioritizer review (#9).*

| Trigger | Action |
|---|---|
| Diagnostic per-class macro-F1 < 0.6 at S9 close | Halt feature work; reallocate ML + annotation capacity; re-baseline labelling; consider scope cut on diagnostic granularity. |
| DPIA not signed by S5 start | Block all Egypt capture; escalate to counsel; re-plan Sprint 5 to non-Egypt fixtures. |
| App Store first-engagement letter rejected by Apple by S10 | Convene with founder + counsel; rewrite positioning; consider web-fallback path for Solo. |
| Battery drain > 25%/hr on iPhone 13 at S12 | Halt Sprint 13 feature work; perform power profiling sprint; investigate JSI/Fabric overhead. |
| Live feed p95 > 4 s on Wi-Fi at S20 | Reframe Wi-Fi as "post-shot review only"; force USB-C marketing for coaches. |
| SOC 2 Type I auditor flags major control failure at S22 | Block launch announcement; remediate before public launch. |
| Pen-test critical finding unresolved at S24 start | Block public launch until resolved. |

---

## 8. Cross-references

- **Architecture:** `docs/architecture/master.md`, `docs/architecture/data-model.md`, `docs/architecture/adr/ADR-0001-react-native-new-architecture.md`, `docs/architecture/adr/ADR-0002-python-fastapi-backend.md`, `docs/architecture/adr/ADR-0003-gopro-labs-firmware-commit.md`, `docs/architecture/adr/ADR-0004-usb-c-federation-p0.md`, `docs/architecture/adr/ADR-0005-rtmpose-x-pose-backbone.md`, `docs/architecture/adr/ADR-0006-multi-task-hierarchical-diagnostic-head.md`, `docs/architecture/adr/ADR-0007-watermelondb-offline-first.md`, `docs/architecture/adr/ADR-0008-imu-bnde-stockmount.md`, `docs/architecture/adr/ADR-0009-onnx-tensorrt-quantization.md`.
- **Security:** `docs/security/threat-model.md`, `docs/security/qr-checkin-token-spec.md`, `docs/security/audit-logging-spec.md`, `docs/security/right-to-erasure-cascade.md`.
- **Compliance:** `docs/compliance/dpia.md`, `docs/compliance/pdpc-application.md`, `docs/compliance/joint-controller-template.md`, `docs/compliance/consent-form-art9.md`, `docs/compliance/rope-art30.md`.
- **ML:** `docs/ml/pose-backbone-eval.md`, `docs/ml/diagnostic-head-spec.md`, `docs/ml/calibration-protocol.md`, `docs/ml/active-learning-queue.md`, `docs/ml/validity-study-protocol.md`.
- **Reviews referenced:** `docs/reviews/01-ai-engineer.md`, `docs/reviews/02-architect-reviewer.md`, `docs/reviews/03-mobile-developer.md`, `docs/reviews/04-performance-benchmarker.md`, `docs/reviews/05-embedded-firmware-engineer.md`, `docs/reviews/06-trend-researcher.md`, `docs/reviews/07-compliance-auditor.md`, `docs/reviews/08-sprint-prioritizer.md`, `docs/reviews/09-ux-researcher.md`, `docs/reviews/10-devops-automator.md`.
- **Risk register:** `docs/risk-register.md`.

---

## 9. Post-V1 roadmap reference

### V1.1 (immediately post-launch)
- Top issues from real-user feedback.
- Performance optimizations on production data.
- Critical bug fixes.
- Onboarding improvements from conversion analysis.

### V1.5 (after first significant user base)
- Trap + FITASC discipline ML release (scaffolding from Sprint 15).
- Spanish localization.
- HealthKit / Health Connect; Whoop / Oura integrations.
- Chest-strap HR for shot-level analysis.
- Two-camera synchronized capture in production (architecture-only in V1).
- On-prem federation deployment validated.
- Microphone array (4-mic) hardware SKU + TDOA shot localization.
- Gaze-tracking front-camera path (L2CS-Net + 6DRepNet).
- 3D triangulated pose (VoxelPose / MvP).
- LoRA fine-tune on Franco-corrected outputs.
- Voice-note transcription.
- Coaching-certification program for AIMVISION-affiliated coaches.

### V2 (federation tier scaling)
- Custom IMU hardware SKU (shotgun-specific).
- AIMVISION Camera Kit (bundled hardware).
- Multi-federation cohort analytics with cross-federation consent rails.
- Validity studies submitted to peer-reviewed sport-science journals.
- Asia-Pacific market expansion.
- Series A.

### V3+
- Custom AIMVISION hardware (replacing GoPro for federation tier).
- Adjacent disciplines (pistol/rifle if technical pivot warrants).
- VR/AR integration possibilities.
- Coaching marketplace network.

---

**Document maintenance:** Owner: CTO Hany Sadek. Review cadence: each phase gate. Update process: sprint outcomes captured in retros, plan adjusted at phase boundaries from observed velocity and learning.

— END OF V2 SPRINT BUILD PLAN —
