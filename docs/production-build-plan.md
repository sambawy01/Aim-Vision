# AIMVISION — Production Build Plan

> **Status:** Draft for team review — generated 2026-05-24 after a deep-dive
> session that took the mobile app from "never built end-to-end on a modern
> Mac" (Phase-0 scaffold) to "boots on iPhone 16e sim with capture, login,
> and pipeline wiring." This plan scopes the work between **today** and
> **General Availability** (GA) of the AIMVISION product to the Egypt
> National Team and the first paying clubs.
>
> Source-of-truth claims: [`CLAUDE.md`](../CLAUDE.md),
> [`docs/AIMVISION_V2_Sprint_Plan.md`](AIMVISION_V2_Sprint_Plan.md),
> [`docs/architecture-overview.md`](architecture-overview.md), the ADRs
> under [`docs/adr/`](adr/), and the compliance + security folders.

---

## 1 · Outcome

A production-grade AIMVISION stack — coach dashboard (web), athlete + coach
mobile app, ML observation pipeline, and federation tier — that an Egypt
National Team coach can sign in to on day-one and capture, analyze, and review
clay/skeet sessions end-to-end. Compliant with **GDPR**, **COPPA**, and
**Egypt PDPL**. Multi-tenant SaaS with optional on-prem federation deploy.

**Definition of production-grade** (the bar):
- **Compliance**: verifiable parental consent, server-enforced age gate,
  audit-chained data access, right-to-erasure, DPIA/RoPA on file.
- **Security**: OIDC-grade auth, TLS pinning, secrets in KMS, rate limits,
  threat-modelled per [`docs/security/threat-model.md`](security/threat-model.md).
- **Reliability**: SLOs declared, error budgets tracked, on-call rotation
  documented. P95 latencies inside `docs/performance-budgets.md`.
- **Observability**: traces + metrics + logs + crash analytics, symbolicated.
- **Quality**: every release gated by full CI (incl. mobile native build),
  ML promotion gates from `aimvision-ml/eval/gates.py`, manual smoke on the
  pilot range before any version reaches a customer.
- **Operational maturity**: documented runbooks, backup/restore tested,
  on-prem Helm chart deployable by a non-author.

**Non-goals for this plan** (Phase-2 or later):
- Custom AIMVISION sensor hardware (BMI270 IMU rig) — Phase 2.
- Public-marketing website / Stripe billing UI for Solo tier — post-pilot.
- Mobile-side ML inference (server-side stays the source of truth in V1).

---

## 2 · Where we are today

The end of the deep-dive session leaves the following PRs open or merged:

| PR | Scope | Status |
|---|---|---|
| #85 | Right-to-erasure web UI | Merged |
| #86 | ML per-class recall gate (S6) | Merged |
| #87 | Mobile phone-capture feature flag (ADR-0009 gate) | Merged |
| #88 | Login contract + pickers + athlete seed | Merged |
| #89 | Auth refresh tokens + tenant switching | Open, CI passing |
| #90 | Mobile capture → upload seam + working login | Open |
| #91 | Mobile local launch (TS plugin → JS, assets, deps) + runbook | Open |
| #92 | **RN ecosystem modernization** (Expo 51 → 56, RN 0.76 → 0.85, screens 3 → 4.25, React 18 → 19, plus 13 platform-drift fixes) — *app now boots on the iOS Sim* | Open |

What is genuinely **built and verified** today:

- Web coach dashboard: athletes, sessions (with shots from the ML pipeline),
  erasure UI, federation tier, EN/AR i18n, role-gated nav.
- Mobile app: boots; onboarding flow walkable (age gate → adult/minor/COPPA
  branches); login screen; capture screen (no live camera in sim, real on
  device); upload to backend wired.
- Backend: FastAPI + SQLAlchemy 2 + Alembic + RLS, JWT auth (stub-grade),
  multi-tenant, hash-chained audit log, drill catalog, coaching-note
  persistence, right-to-erasure foundation (crypto-shred + ledger).
- ML: classical audio shot detector (works on real WAVs today — used to
  drive 12 detected shots into a session in the live demo), pose eval
  harness, diagnostic eval harness with per-class recall gate, LLM
  coaching-note pipeline with verifier (deepseek/qwen via Ollama).
- Camera: mock backend, in-tree phone-capture native plugin (Swift +
  Kotlin + Rust C-ABI bridge) — *runtime never verified on device*.
- Infra: Helm chart + CloudNativePG groundwork (ADR-0005), GitHub Actions
  CI per sub-repo + orchestrator.

What is **scaffold or stub** (load-bearing for production, not yet real):

- Auth: PBKDF2 + `dev-secret-change-me-in-production` JWT. No OIDC, no
  refresh-on-401 loop on mobile, no password reset, no rate limiting, no
  TLS pinning.
- Verifiable parental consent: UI shells; no Stripe / Veriff / Zoom / DocuSign
  integration; `/auth/parental-consent` backend endpoint **does not exist**.
- Age gate: client-side only — no server enforcement.
- GoPro Hero 13 capture: not built (hardware-gated).
- WatermelonDB offline sync: 613-line TS scaffold; `@nozbe/watermelondb`
  is not installed; runs against an in-memory map in tests.
- On-device ML: no model deployed to the mobile app.
- Sentry: runtime SDK loads; no symbol upload (no credentials).
- Statsig: stubbed; useFlag falls back to defaults.
- OTel: placeholder; no exporter wired.
- Ambient-light sensor for RangeMode: provider exists, sensor unread.

Honest split: roughly **30-40 % built end-to-end**, **30-40 % scaffold or
stub**, **30 % hardware- or external-integration-gated**.

---

## 3 · Workstreams

Twelve workstreams. Each lists scope, current state, the integrations it
needs, the team it needs, and a rough effort range. Effort is in
**engineer-weeks** assuming the staffing in §5 — multiply by N for parallel
work, add a 25 % buffer for the unknown.

### A · Production auth & identity

**Scope.** Replace the stub auth with an OIDC/OAuth2 identity layer:
argon2id passwords, refresh token rotation, password reset, email
verification, login rate limiting, server-side session revocation, TLS
pinning at the native layer.

**Current.** PBKDF2 + dev-secret HS256 JWT (`services/auth.py` literally
says *"Stub for the production PASETO/OIDC path"*). Web has refresh +
tenant-switch endpoints (#89). Mobile has no refresh-on-401. No password
reset, no email verification, no rate limiting.

**Integrations needed.**
- **Supabase Auth (GoTrue)** — self-hosted per ADR-0010 to match the
  on-prem-first GA (ADR-0012). GoTrue is the JWT issuer + user store +
  password-reset + email-verify path; the AIMVISION backend keeps its
  tenancy / memberships / RLS layer and validates Supabase-issued JWTs.
- TLS pinning library on iOS (URLSession `serverTrust` evaluator) and
  Android (OkHttp `CertificatePinner`).
- An email provider for verification / password reset (Postmark / SES for
  cloud; **`smtp4dev` or a federation's own SMTP** for on-prem).
- Recommended: **Cloudflare Bot Management** for login rate limiting
  beyond what FastAPI middleware + GoTrue's per-user limits give us.

**Migration.** Existing PBKDF2 + dev-secret-JWT users get bulk-imported into
GoTrue (`auth.users.encrypted_password = '$pbkdf2$…'`) so the next login
on the new stack succeeds without forcing a password reset.

**Effort.** **3–4 weeks** with one senior backend + one mobile dev.

**Acceptance.**
- Argon2id hashing live; old PBKDF2 users migrated on next login.
- Refresh-on-401 working on both web and mobile.
- Login + password reset rate-limited to 5/min/IP, 20/hour/account.
- Penetration test (or `aimvision-backend` `cso` skill audit) reports no
  high-severity auth findings.

---

### B · Verifiable parental consent & age enforcement

**Scope.** Make COPPA / GDPR / PDPL minor consent **real** — backend endpoint,
integrations with the four UI methods, server-side age enforcement, audited
consent ledger, and consent revocation flow.

**Current.** Mobile UI for all four verification methods (paper PDF, credit
card, email+ID, video call) exists and is polished. Backend endpoint
**does not exist**. Age gate is client-side only. Consent matrix grants are
backend-persisted but the parental tie-in is missing.

**Integrations needed (one per method, choose at least two for launch).**
- **Paper PDF + ID upload**: object storage for the PDF (S3/GCS) + a
  background-checked human review queue (LiveOps tooling — Notion/Linear
  works for a small queue).
- **Credit-card verification** (the most automatable): **Stripe** *Setup
  Intent* + immediate refund of the auth (COPPA §312.5(b)(2)(ii)). Stripe
  has no per-event fee for $0 auth + refund. Estimated cost: ~$0.30 per
  consent.
- **ID verification** (the gold standard for federations): **Veriff** or
  **Persona** — both serve the EU + MENA. ~$1.50–$3.50 per check.
- **Video verification call**: **Twilio Video** *or* **Daily** (cheaper) —
  integrate scheduling + recording-with-consent + retain for the audit log.

**Other backend work**:
- New `/auth/parental-consent` endpoint + Temporal workflow per
  [`docs/compliance/parental-consent-flow.md`](compliance/parental-consent-flow.md).
- Server-side age check on every authenticated request (currently only the
  client UI gates).
- Consent ledger table (similar to `erasure_tickets`) so a parent can later
  revoke and we have proof of the original grant.
- DSAR + erasure tie-in: a minor's erasure request must notify the parent.

**Effort.** **4–5 weeks** with one backend dev + one mobile dev + design
review + **specialist counsel — Phase-1 gate, not optional** per ADR-0015
(Phase 1 ships full minor-athlete support). See §6.

**Scope at launch per ADR-0011.** Stripe card verification is the *only*
active method in Phase 1; the other three UI methods (paper PDF, email +
ID, video call) stay in the codebase but their backend routes return 410
Gone behind a runtime flag. They re-enable in a Phase-2 enhancement once
Stripe alone has surfaced consent-flow operational gaps.

**Acceptance.**
- All four UI methods reach a verified state in staging using sandbox
  credentials of the integration.
- A signed RoPA + DPIA on file in `docs/compliance/` covering each
  integration's data flow.
- A consent revocation tested end-to-end (parent revokes → minor account
  pauses next request).

---

### C · Camera & capture moat — GoPro Hero 13 + multi-camera sync

**Scope.** The product camera path: pair a Hero 13 to the mobile app via
USB-C or Wi-Fi, stream live preview to the coach's phone, capture full-fidelity
video + audio + metadata, upload chunked recordings, and run multi-camera
clock synchronization for the federation rig.

**Current.** Phone-capture dev backend (ADR-0009) is real and now boots.
Hero 13 integration is **not built**. Multi-camera sync spec
(`docs/multi-camera-sync-spec.md`) defines `!MSYNC` + audio cross-correlation;
the cross-correlation algorithm and ChArUco calibration math are
implemented in `aimvision-ml/`. The mock camera works (PR #77 synthesizes
shot-detectable audio).

**Integrations needed.**
- **GoPro Hero 13 hardware** (procurement — see §6).
- **Open GoPro SDK** for iOS and Android (free, but currently
  out-of-the-box experience is rough — see `docs/camera-integration-spec.md`
  on the "Open GoPro reality" gap; expect significant adaptation work).
- **GoPro Labs firmware** for `!MSYNC` and `!HILIGHT` (Labs is free but
  research-grade — wire only after firmware-matrix validation per
  `docs/camera-integration-spec.md`).
- **USB-C UVC tether** mode for the federation tier — `docs/architecture-overview.md`
  upgrades this from P1 to P0 per the perf review.
- **AWS S3** *or* **on-prem MinIO** for recording storage (currently local-fs
  per `services/storage.py`); resumable multipart uploads, server-side
  encryption with per-tenant DEKs from the right-to-erasure layer.

**Mobile work**:
- BLE-discovery + Wi-Fi pair-and-stream control plane.
- Background upload with retry queue (poor range Wi-Fi is the assumption).
- Session-picker UI on mobile (today the capture screen wants a pasted
  session id).
- Real-time fps / battery / thermal HUD per `docs/mobile-architecture.md` §9.

**Effort.** **6–8 weeks** with one senior mobile dev + one camera/native
specialist. Hardware-gated: needs at least two Hero 13s in hand.

**Acceptance.**
- A coach pairs a Hero 13, captures a 5-minute session, the recording
  uploads while the range Wi-Fi is intentionally throttled, the
  post-session pipeline runs, and a coaching note renders on the web
  dashboard. Same flow works for a 2-camera federation rig with
  cross-correlation alignment ≤ 50 ms.

---

### D · ML pipeline — real models, real coaching notes

**Scope.** Train the diagnostic models on real range footage, deploy them
to the ML worker pool, validate the LLM coaching-note quality with real
coaches, lock the diagnostic taxonomy via card-sort.

**Current.** `aimvision-ml/` has the *infrastructure* (eval gates, audio
shot detection, pose eval harness, synthetic data generators, LLM
coaching-note pipeline with verifier, MLflow client). What is missing
is the *trained models*: RTMPose-x not trained on shooter footage,
diagnostic head not trained, DeepSeek 14B not fine-tuned, LoRA per-athlete
adapters not built.

**Integrations needed.**
- **GPU compute** (pose + diagnostic training only): AWS A10G / L4
  (~$0.50–$1/hr) or on-prem RTX 4090s. T4 is too slow for RTMPose-x per
  `docs/ml-architecture.md`. No GPU needed at inference time — pose /
  diagnostic models run on CPU + ONNX Runtime in the ML worker pool.
- **MLflow Tracking** (already integrated client-side) — needs a hosted
  server (Databricks Community Edition or self-hosted).
- **Hosted LLM API** for coaching-note generation per ADR-0014. Vendor
  selection (Anthropic Claude / OpenAI GPT-4o / Together AI hosted Llama
  3.1 70B / etc.) is workstream D's week-1 task. Supersedes the original
  DeepSeek-via-Ollama plan from `docs/ml-architecture.md`.
  - **PII strip is now load-bearing.** `aimvision_ml.llm.pii` runs on
    every prompt before the on-prem deployment egresses to the hosted
    endpoint. Document the data flow for the Egypt federation
    procurement review.
  - Federation egress carve-out (post-Phase-1): if a specific federation
    contractually disallows internet egress, wire a self-hosted smaller
    LLM via Ollama as a fallback. Not in Phase 1.
- **Synthetic + real data**: synthetic harness already in `eval/synth_*.py`;
  real data is the **chicken/egg** problem (see §8 risks).

**Workstreams sub-tasks**:
- D1: Collect 50+ hours of real range footage with consent (waits on
  workstreams B + C).
- D2: Fine-tune RTMPose-x on shooter stances (12-coach card-sort first
  per `docs/diagnostic-taxonomy.md` Sprint-9 gate).
- D3: Train the multi-task hierarchical diagnostic head.
- D4: DeepSeek 14B LoRA fine-tune on Franco-corrected coaching notes.
- D5: Promotion-gate every candidate model through the §13 gates already
  in `aimvision-ml/eval/gates.py` — bias-axis F1 spread ≤ 0.05, per-class
  recall floor (the PR #86 addition), ECE ≤ 0.05, top-3 macro-F1 ≥ 0.78,
  conformal coverage ≥ 0.88.

**Effort.** **8–12 weeks** (parallel with B+C), one ML engineer + GPU access
+ active access to real footage from the Egypt pilot.

**Acceptance.**
- All three model types pass the §13 promotion gate on a held-out test set.
- 10-coach blind review of coaching notes: ≥ 70 % "would say this to my
  athlete" rate.

---

### E · Mobile app — production hardening

**Scope.** Take the modernized mobile app (PR #92) from "boots in sim" to
"shippable to TestFlight / Play Store internal track."

**Current.** As of #92: Expo SDK 56, RN 0.85, React 19. Compliance UI,
login, capture, upload, RangeMode, i18n all real. Statsig stubbed.
WatermelonDB not installed. Refresh-on-401 not wired.

**Sub-tasks**:
- E1: Replace Statsig with a React-19-compatible flag SDK — **ConfigCat**
  is the lowest-friction (REST API, no React peer-dep coupling).
- E2: Install + wire **`@nozbe/watermelondb`** and connect it to the
  pure-TS sync engine in `src/sync/`. Schema migrations.
- E3: Real **OTel exporter** (Honeycomb or Grafana Cloud) — mobile-side
  traces for capture latency.
- E4: Sentry creds — `SENTRY_ORG`, `SENTRY_AUTH_TOKEN` in EAS secrets +
  re-enable the `@sentry/react-native` plugin entry I removed today.
- E5: Mobile refresh-on-401 loop (mirror what `aimvision-web/src/services/api.ts`
  does, adapted for SecureStore + native cookie store).
- E6: Real `assets/` icons (1024×1024 brand artwork — not the 1×1
  placeholder PNGs PR #91 committed).
- E7: App store metadata (privacy nutrition labels, ATT, screenshots).
- E8: Root / jailbreak detection (`react-native-device-info` +
  `react-native-iroot-detection`).
- E9: EAS Build pipeline → TestFlight + Play Store internal track.

**Effort.** **3–4 weeks**, one mobile dev.

**Acceptance.**
- TestFlight build accepted, no critical Sentry issues for 7 days with 5+
  internal users.
- WatermelonDB sync running against a real backend in spotty-Wi-Fi mode.

---

### F · Backend — production hardening

**Scope.** Migrate the SQLite dev backend to Postgres with RLS validated,
swap local-fs storage for S3, wire Temporal for post-session orchestration,
finish the right-to-erasure sub-processor fan-out, add multi-tenant
isolation tests under load.

**Current.** SQLite default works; Postgres path with RLS migrations exists
(alembic 0003) and CI runs the Postgres test suite. `services/storage.py`
has a Storage protocol; LocalFsStorage is the only impl. Temporal client
adapter exists, no workflow wired end-to-end. Right-to-erasure foundation
shipped (#84) — crypto-shred + ledger; sub-processor fan-out + 30-day grace
workflow not built.

**Integrations needed.**
- **CloudNativePG** (ADR-0005) — already groundwork in `aimvision-infra/`.
- **Temporal Cloud** *or* self-hosted Temporal cluster (ADR-0007).
- **AWS S3** (cloud tier) and **MinIO** (on-prem tier) behind the same
  Storage protocol — recording uploads, audit chain snapshots, DEK
  wrap material.
- **AWS KMS** (cloud) / **HashiCorp Vault** (on-prem) for the per-tenant
  DEKs that the right-to-erasure layer assumes.

**Sub-tasks**:
- F1: S3Storage impl; SSE-KMS with per-tenant DEK; resumable multipart for
  large recordings.
- F2: Migrate `data_encryption_kek` out of `config.py` into KMS/Vault.
- F3: Temporal workflows: post-session (ingest → align → diagnostic → note),
  right-to-erasure (grace-period + sub-processor fan-out).
- F4: Load-test RLS isolation: 1k concurrent tenants, no cross-tenant leaks
  surfaced by the `cso` skill's STRIDE pass.
- F5: Backup/restore: `pg_dump` + audit-chain verification on restore.

**Effort.** **5–6 weeks**, one backend dev + one infra collaborator.

**Acceptance.**
- Full app suite passes against managed Postgres in CI + a staging deploy.
- Recording upload + S3 storage end-to-end with 4 GiB stress-test files.
- Temporal post-session workflow visible in the Temporal UI with retry
  visibility.

---

### G · Web dashboard — production polish

**Scope.** The web dashboard is the most mature surface; finish the rough
edges and harden for federation-admin use.

**Current.** Sessions list/detail/create with real backend, federation
dashboard (#38), erasure UI (#85), coaching-note rendering (#81),
tenant switcher, EN/AR + RTL, role-gated nav.

**Sub-tasks**:
- G1: Fix the stale "/v1/federation not yet implemented" comment in
  `services/federation.ts` (the endpoints exist now).
- G2: Session detail shows raw UUIDs; render athlete display name +
  human-friendly session title.
- G3: WAL + busy-timeout on SQLite for the local dev artifact 5-second
  slow-create (alternatively: switch local dev to Postgres). Real fix
  for production is just "use Postgres."
- G4: Real-time updates: server-sent events or websockets for post-session
  pipeline status (today the dashboard polls).
- G5: Accessibility audit (axe / Lighthouse) — `aimvision-web/src/components/a11y/`
  is a good base.
- G6: Web-vitals + Sentry RUM for performance budgets.

**Effort.** **2–3 weeks**, one frontend dev.

**Acceptance.**
- Lighthouse a11y + performance scores ≥ 90.
- Coach demo flow on the pilot range works end-to-end with no UX papercuts.

---

### H · Observability & SRE

**Scope.** Tie everything together with traces, metrics, logs, crash
analytics, SLOs, and an on-call rotation.

**Integrations needed.**
- **Sentry** (cloud) or **GlitchTip** (self-hosted) — crashes + RUM, with
  symbol upload for the mobile app.
- **Honeycomb** *or* **Grafana Cloud** — OTel traces + metrics.
- **Loki** + **Promtail** — logs (matches Helm-chart-friendly stack).
- **PagerDuty** *or* **Opsgenie** for the on-call rotation.

**Sub-tasks**:
- H1: SLOs declared per `docs/observability-plan.md` (P95 capture-to-note
  latency, error budget per endpoint, mobile crash-free rate).
- H2: End-to-end trace: mobile capture → upload → backend ingest → ML
  worker → coaching-note generation → web rendering — one trace id.
- H3: Incident-response playbooks for: tenant data leak, ML model
  regression, federation on-prem outage, KMS rotation failure.
- H4: Synthetic monitor: a "canary tenant" runs a scripted session every
  10 minutes against staging.

**Effort.** **2–3 weeks**, one infra dev (overlaps with workstream F).

**Acceptance.**
- A practiced incident response (game-day) resolves a synthetic ML model
  regression in < 30 min.
- Crash-free rate of mobile builds > 99.5 % over 7 days.

---

### I · Infrastructure & DevOps

**Scope.** One Helm chart, cloud + on-prem parity (ADR-0005), CI/CD that
catches the next platform-drift wall before a human hits it.

**Current.** Per-repo CI on GitHub Actions, plus an orchestrator workflow.
Mobile CI runs lint / typecheck / jest — **does not prebuild, does not
xcodebuild** (which is how the 13 walls in #92 got missed).

**Sub-tasks**:
- I1: Mobile CI — add an `expo prebuild --platform ios --no-install` smoke
  step. (Catches plugin / config / asset regressions of the class #91
  documented.)
- I2: Mobile CI — add a periodic full `expo run:ios` against an iOS
  simulator runner (catches xcodebuild-only regressions of the class #92
  fixed).
- I3: EAS Build for app store releases + TestFlight + Play Store internal
  track auto-uploads.
- I4: Helm chart: federation-tier on-prem deployment as a 1-shot
  `helm install`, with the CloudNativePG cluster, MinIO, Ollama, Temporal
  worker, and ML worker all in one release.
- I5: Secret rotation runbook: KMS keys (90-day), JWT secret (per release),
  Sentry tokens.
- I6: Backup/restore drill: take a tenant's full data out, verify hash
  chain, restore to a different cluster, prove the audit chain still
  validates.

**Effort.** **4–5 weeks**, one DevOps lead.

**Acceptance.**
- Helm `install` to a fresh k3s cluster yields a working federation tier in
  ≤ 15 minutes.
- Mobile CI catches a deliberate `expo prebuild`-breaking change in PR
  review.

---

### J · Hardware procurement & field trials

**Scope.** Get the camera in hand, run the Egypt pilot, harvest the first
real range data.

**Sub-tasks**:
- J1: Purchase order: **6 × GoPro Hero 13** + chest/helmet mounts +
  USB-C tether cables + spare batteries. ~$3,500.
- J2: Optional: 2 × Sony A7C II as a federation-tier USB-C UVC alternative
  per the perf review (~$5k).
- J3: **Egypt National Team facility** pilot scheduling per ADR-0016
  (the design partner per CLAUDE.md; supersedes the earlier
  Cairo-Shooting-Club default). National Team coaching staff are the
  in-region champions + the source-of-truth coaches for D2's card-sort
  + D4's coaching-note review.
- J4: Range data harvest with consent (workstreams B + C must be live).
- J5: Field-data feedback loop into workstream D (ML training).

**Effort.** **4–6 weeks** elapsed, 1 PM + 1 in-region champion. Money +
calendar more than dev effort.

**Acceptance.**
- One coach + four athletes run a full session at the pilot range, get
  coaching notes the same day, and rate the notes ≥ 7/10.

---

### K · Documentation & onboarding

**Scope.** External coach + federation-admin onboarding, internal SOPs,
public privacy policy + ToS.

**Sub-tasks**:
- K1: Coach onboarding doc (Notion / docs site): "your first session in
  five minutes."
- K2: Federation-admin operations guide.
- K3: Privacy policy + Terms of Service finalized by counsel.
- K4: API reference auto-published from `aimvision-backend`'s OpenAPI
  (already generates `openapi.json`).
- K5: Internal runbooks: incident response, key rotation, on-call.

**Effort.** **2 weeks** technical writing (parallel with later phases).

---

### L · Legal & compliance review

**Scope.** Independent counsel review of: COPPA + minor-in-shooting-sports,
Egypt PDPL specifics, EU SCCs for the Egypt → EU/US transfer if applicable,
firearms-adjacent-content disclosure for App Store / Play Store reviews.

**Effort.** **1–2 sessions with specialist counsel + 1 internal
counsel-of-record relationship.** Money + calendar.

**Acceptance.**
- Counsel sign-off on: parental-consent flow, age gate, retention policy,
  data-classification per `docs/compliance/data-classification.md`.

---

## 4 · Phasing & timeline

Twelve workstreams, three phases. Times in **calendar weeks** assuming the
staffing in §5; serial dependencies are called out. Mark **(parallel)**
work that can run alongside.

### Phase 1 — **Foundation** (weeks 1–4)

Lock in everything a customer's coach needs on day-one before they ever
sit on a range.

| Wk | Auth (A) | Compliance (B) | Backend (F) | Web (G) | Obs (H) | Infra (I) |
|---|---|---|---|---|---|---|
| 1 | OIDC vendor selected, integration POC | Counsel kickoff, `/auth/parental-consent` API contract | Postgres staging stand-up | (parallel) G1 fed comment | OTel pilot trace | I1 mobile-ci prebuild step |
| 2 | argon2id migration, refresh-on-401 backend | Stripe Setup Intent POC | S3 storage impl | G2 athlete-name display | Sentry creds + RUM | I3 EAS Build |
| 3 | TLS pinning iOS + Android | Veriff + DocuSign sandbox | KMS-backed DEK | G5 a11y audit | SLOs declared | I4 Helm chart end-to-end |
| 4 | Password reset + email verify + rate limits | Temporal consent workflow | Right-to-erasure fan-out | G6 RUM | Incident playbook drill | I5 secret rotation runbook |

**Phase 1 gate.** A coach can sign up with email verification, a minor's
parent can complete verifiable consent through at least Stripe + DocuSign,
all data lands in Postgres with KMS-wrapped DEKs, every request is in a
Sentry-and-Honeycomb trace, the Helm chart deploys cleanly. Both web and
mobile login work end-to-end through the new auth layer.

### Phase 2 — **Capture moat** (weeks 5–10)

The camera is in hand and the observation pipeline is real.

| Wk | Camera (C) | ML (D) | Mobile harden (E) | Hardware (J) |
|---|---|---|---|---|
| 5 | Hero 13s arrive; Open GoPro POC | (parallel) D1 begin data collection | E1 ConfigCat | J1 HW PO landed |
| 6 | BLE + Wi-Fi pair-and-stream | D5 promotion-gate harness wired to MLflow | E2 WatermelonDB | J3 pilot scheduling |
| 7 | USB-C UVC federation rig | First synthetic-trained RTMPose pass | E5 mobile refresh-on-401 | (parallel) J5 feedback loop start |
| 8 | Multi-camera sync end-to-end | Diagnostic head training on partial data | E4 Sentry symbols | |
| 9 | Background upload + retry queue | DeepSeek LoRA prep | E7 store metadata | |
| 10 | Capture + upload + pipeline glue (one trace) | First coaching-notes generated on real footage | E9 EAS → TestFlight + Play internal | |

**Phase 2 gate.** A Hero 13 + iPhone + backend + web dashboard chain
produces a coaching note on a real shooter session within 10 minutes of
the last shot. Crash-free rate > 99 % for the internal cohort.

### Phase 3 — **Pilot + GA hardening** (weeks 11–16)

| Wk | Pilot (J) | ML (D) | Cross-cutting |
|---|---|---|---|
| 11 | First Cairo range session | Eval gates on real data, regressions caught | Tighten anything Phase 2 surfaced |
| 12 | Daily session loop, real coach feedback | LoRA fine-tune on actual coaching corrections | |
| 13 | Federation rig (multi-camera) at the range | Per-athlete LoRA proof-of-concept | |
| 14 | Internal-to-external coach handoff | Promotion-gate the production model | K1 + K2 docs finalized |
| 15 | Two weeks soak; track Sentry + SLOs | | L final counsel sign-off |
| 16 | GA flip; first paying club | | Post-mortem + V2 roadmap |

**Phase 3 gate (GA).** 30 consecutive days of pilot use with:
- Mobile crash-free > 99.5 %.
- All P95 latencies inside `docs/performance-budgets.md`.
- No high-severity security findings open.
- ≥ 1 federation admin running the on-prem Helm deploy themselves.
- Documented incident response actually exercised twice (game days).

**Total elapsed.** **~16 weeks (4 months)** with the team in §5.

---

## 5 · Team & resourcing

Realistic minimum to hit the timeline above:

| Role | Headcount | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|---|
| Backend (Python/FastAPI/Postgres) | 2 | A, F | F (less) | hardening |
| Mobile (RN + iOS/Android native) | 2 | A, B (UI) | C, E | pilot fixes |
| ML engineer | 1 | (idle/data prep) | D | D + LoRA |
| Camera/native specialist | 1 | (idle/research) | C | pilot support |
| DevOps / SRE | 1 | F, H, I | I, H | on-call lead |
| Frontend (web) | 1 | G | G (light) | pilot polish |
| Design | 0.5 FTE | B (consent UX) | E (mobile polish) | pilot fixes |
| PM | 1 | All | All | All |
| Legal (specialist counsel + in-house) | external | B, L | (parallel) | L sign-off |

**~7.5 FTE** for 4 months. If the team is smaller (e.g., 3 FTE), expect
~9–10 months elapsed and reorder Phase 2 to start ML data collection in
parallel with auth/compliance — the chicken-and-egg between footage and
trained models is otherwise the long pole.

---

## 6 · Procurement & vendor decisions

The integrations that need a purchase decision **before week 1**:

All seven §10 decisions resolve; this table reflects the chosen path
(on-prem-first, Supabase auth, Stripe-only consent, Android-first
rollout, hosted LLM, full minor support).

| Item | Vendor (chosen / decision) | Approx. cost | Owner |
|---|---|---|---|
| Identity (ADR-0010) | **Supabase Auth (GoTrue), self-hosted** | infra only | Backend lead |
| Email (verify / pw-reset) | Postmark or SES; federation can BYO SMTP | $10/mo + per-email | Backend lead |
| Card verification, consent (ADR-0011) | **Stripe** (Setup Intent + refund) | ~$0.30 / consent | Compliance lead |
| ID / video / document-signing | *Deferred to Phase 2 enhancement per ADR-0011* | — | — |
| Coaching-note LLM (ADR-0014) | Anthropic Claude / OpenAI GPT-4o / Together AI hosted Llama 3.1 70B (pick week-1 of D) | $0.15–$3 / 1M input tokens | ML lead |
| Crash analytics | **GlitchTip self-hosted** (on-prem default) — Sentry SaaS available as a cloud add-on | infra only | DevOps |
| Tracing / metrics | **Grafana Cloud free** *or* self-hosted Prometheus + Tempo | $0 – $200/mo | DevOps |
| Logs | Loki self-hosted | infra cost only | DevOps |
| On-call | PagerDuty / Opsgenie | $21/user/mo | SRE lead |
| Feature flags | ConfigCat / Unleash | $0 – $80/mo | Mobile lead |
| Object storage | **MinIO (on-prem default)** — S3 available as a cloud add-on | infra cost only | Infra lead |
| KMS / secrets | **HashiCorp Vault (on-prem default)** — AWS KMS as cloud add-on | infra cost only | Security lead |
| GPU compute (training only) | AWS A10G / L4 *or* on-prem RTX 4090 | $0.50–$1/hr cloud | ML lead |
| MLflow tracking | Self-host | infra cost only | ML lead |
| Hardware | 6 × Hero 13 + mounts | ~$3,500 | PM |
| App stores (Android first per ADR-0013) | **Google Play** ($25 one-time); Apple Dev maintained for builds, not first release | $25 (+ $99/yr iOS later) | PM |
| **Counsel** *(Phase-1 gate per ADR-0015)* | Specialist (children's data + firearms-adjacent + Egypt PDPL) | Hourly | Founder/CEO |

Estimated **first-year recurring integration spend (excluding salaries +
infra + hardware):** **$2k–$8k** (the on-prem-default story drops Sentry
SaaS, Auth0 / WorkOS, and the deferred consent vendors), plus per-consent
variable cost (~$0.30 × N athletes onboarded) and per-token LLM cost
(small for short structured outputs).

---

## 7 · Acceptance gates per phase (compact)

| Phase | Gate |
|---|---|
| 1 | Production auth working on web + mobile; consent integrations submit-and-verify through Stripe + DocuSign sandbox; Helm chart deploys cleanly; Sentry shows real (non-test) traffic. |
| 2 | One Hero 13 + one iPhone + backend = a coaching note on a real shooting session. Multi-camera sync ≤ 50 ms. Crash-free > 99 %. |
| 3 (GA) | 30 days with crash-free > 99.5 %, all SLOs met, federation admin self-deploys Helm chart, two game days passed, counsel sign-off final. |

---

## 8 · Risks & mitigations

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| **Chicken/egg on ML training data** — can't train without real footage; can't collect footage without consent + camera | High | High | Start workstream J data collection on day-one of Phase 2 with synthetic + Phase-1's working consent flow. Don't gate Phase 1 on having footage. |
| **App Store review flags firearms-adjacent app** | Medium | High | Apply Apple Game Plan; pre-clear with App Review via Resolution Center. Have counsel-vetted disclosure ready. |
| **GoPro Open GoPro SDK reality** — known rough edges per `docs/reviews/05-embedded-firmware-engineer.md` | Medium | Medium | Federation tier uses USB-C UVC as the P0 fallback. Don't put all eggs in Open GoPro for the federation rig. |
| **Egypt PDPL precedent thin** | Medium | Medium | Use the existing `docs/compliance/egypt-pdpl-action-plan.md` as the starting point; budget for one PDPL specialist consult. |
| **COPPA + minor + firearms interaction** | Medium | High | Specialist counsel review before any < 18 user goes live. Have a "no minors in Phase 1" emergency fallback. |
| **Sentry / OTel cost blows up at scale** | Low | Medium | Self-host GlitchTip + Grafana stack early as a fallback option. |
| **WatermelonDB native install fails on RN 0.85 New Arch** | Medium | Medium | The PR #92 modernization has already verified Hermes/Fabric work; if WatermelonDB still resists, fall back to op-log sync over MMKV until the WatermelonDB Fabric work lands upstream. |
| **Pilot range cancels** | Low | High | Have a US backup range identified by week 8. |

---

## 9 · What this session already shipped vs the plan

This session moved the project meaningfully forward against this plan:

| Workstream | Phase | Done this session |
|---|---|---|
| A (auth) | 1 | Refresh tokens + tenant switching (#89), mobile login fixed (#90) |
| E (mobile harden) | 1–2 | Modernization to SDK 56 / RN 0.85 / React 19 (#92); local launch repeatability (#91); Statsig stubbed; jest unblocked |
| C (camera) | 2 | Capture → upload seam wired (#90); Vision Camera API drift fixes (#92) |
| I (infra) | 1 | The local-launch runbook (#91); identified the mobile-CI gaps for I1 / I2 |
| F (backend) | 1 | Right-to-erasure foundation (#84, already on main); coaching-note + drills + finalize_session endpoints |
| D (ML) | 2 | Per-class recall gate (#86); end-to-end ML demo (12 detected shots into a session via the CLI) |
| G (web) | 1 | Erasure UI (#85), coaching-note rendering (#81), athlete progress (#82), data-fetching bug (#88) |

**Roughly Phase 1 weeks 1–2 of work is already in or in PR review.** The
modernization PR alone unlocks the next 8 weeks of mobile work.

---

## 10 · Open product / engineering decisions

Real decisions that block the plan, in priority order:

### Resolved (2026-05-24)

1. **Identity provider = Supabase (Supabase Auth / GoTrue).** ADR-0010.
   Self-hosted GoTrue fits the on-prem-first GA. Supabase Auth is the
   JWT issuer + user store + password-reset + email-verify path; the
   AIMVISION backend stays the authority on tenancy, memberships, and
   RLS. PBKDF2 users get bulk-imported on the cutover.
2. **Verifiable parental consent at launch = Stripe card verification
   only.** ADR-0011. Stripe Setup Intent + immediate refund of the auth
   (COPPA §312.5(b)(2)(ii)). The other three UI methods (paper PDF,
   email+ID, video call) stay in the codebase but are gated off in
   Phase 1 — they re-enable in a Phase-2 enhancement once Stripe alone
   has surfaced consent-flow operational gaps.
3. **First GA target = on-prem (federation tier).** ADR-0012. Matches
   ADR-0005's "one Helm chart, cloud↔on-prem parity" intent. Drives
   every vendor decision toward something that has a credible
   self-hosted story (Supabase self-host, MinIO, GlitchTip, Grafana
   Cloud-or-self-hosted, Vault). AWS / managed cloud equivalents stay
   available as the cloud-tier add-on, but no Phase-1 work depends on
   them.
4. **First app store = Google Play.** ADR-0013. Android dominates the
   Egypt pilot region's device mix, Play Store review is more permissive
   than Apple's for firearms-adjacent content, and we already have
   `adb` on the dev machine. iOS code stays maintained (capture +
   onboarding work on the Sim today per PR #92), but the first
   external-customer build is the Android one.

5. **Coaching-note LLM = hosted API (not self-hosted Ollama).** ADR-0014.
   Supersedes the `docs/ml-architecture.md` DeepSeek-via-Ollama plan.
   Hosted gives us better-quality output, faster iteration on prompts,
   no GPU procurement on the critical path, and no on-prem-side
   inference cost. Vendor selection (Anthropic Claude / OpenAI / Together
   AI / etc.) deferred to workstream D week 1; the architectural
   commitment is "hosted." `aimvision-ml/src/aimvision_ml/llm/pii.py`
   is now load-bearing: every prompt to the hosted endpoint strips PII
   before it leaves the (potentially on-prem) deployment, and we
   document the data flow for federation procurement reviews.
   Federation carve-out: if a specific federation contractually
   disallows egress, a Phase-2 fallback wires a smaller self-hosted
   model — but this is **not** in Phase 1.
6. **Phase-1 ships full minor-athlete support.** ADR-0015. The
   youth-sports compliance moat is the differentiator and Phase 0's
   age-gate + parental-consent UI is the most-built surface. Shipping
   minors in Phase 1 means: server-side age enforcement is non-optional
   (workstream B), Stripe parental-consent flow must be airtight for
   COPPA, and **specialist counsel review (workstream L) is a Phase-1
   gate, not a Phase-3 nice-to-have**.
7. **Pilot venue = Egypt National Team facility.** ADR-0016. Confirmed
   per CLAUDE.md ("Egypt National Team as design partner") and the V2
   sprint plan's EPIC 5.5. The National Team's coaching staff are the
   in-region champions and the source-of-truth coaches for ML training
   data + coaching-note quality review.

### Open

None — all seven blocking decisions resolved 2026-05-24.

---

## 11 · Out of scope (Phase 2+)

Tracked for after GA so this plan stays focused:

- Custom AIMVISION sensor rig (BMI270 IMU board) — `docs/architecture-overview.md`
  references it as Phase 2.
- On-device ML inference (server-side stays source of truth in V1).
- Stripe billing UI for Solo tier.
- Public marketing site.
- Real-time live commentary mode.
- Multi-language beyond EN + AR.

---

## 12 · How this document gets used

- Owner: PM, with weekly review at the leadership stand-up.
- Workstream leads update their § with status weekly.
- Each acceptance gate is a `gh issue` with a checklist; closing the issue
  flips the gate.
- Decisions (§10) get an ADR each as they're made, filed under
  `docs/adr/0010+`.

When the team has shrunk the open-decisions list and the staffing is
green, this becomes a Gantt and the first sprint cuts.
