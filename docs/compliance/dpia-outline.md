# Data Protection Impact Assessment (DPIA) Outline — AIMVISION

**Status:** Working draft for counsel refinement. Not a finished legal artifact.
**Authority:** GDPR Article 35; Egypt PDPL (Law 151/2020) Article 12; UK Children's Code; COPPA Sec. 312.
**Owner (draft):** Compliance & Privacy Lead → DPO (once appointed, Sprint 1)
**Counsel review required before sign-off:** EU privacy counsel, Egyptian PDPL counsel, UK Children's Code counsel, US COPPA counsel.
**Document version:** 0.1 (Sprint 0 outline)
**Mandatory re-assessment triggers:** every phase gate; new SKU; new federation jurisdiction; addition of IMU stream, gaze tracking, or cross-federation cohort analytics.

> **Reading guide:** every legal-determination point is tagged `[CONFIRM WITH COUNSEL]`. The technical descriptions of processing are authoritative as system-of-record for engineering scope; the lawful-basis and risk-treatment determinations are placeholders pending counsel.

---

## 1. Purpose, Scope, Controllers, Processors

### 1.1 Why this DPIA exists
AIMVISION captures, processes, and infers from biometric and biometric-adjacent data (pose keypoints derived from video; voice notes; optional health and wearable data) of identified athletes, including minors, in multiple jurisdictions. Article 35(3)(a)–(c) GDPR makes a DPIA mandatory for:
- (a) systematic and extensive automated evaluation of personal aspects, including profiling, that produces legal or similarly significant effects;
- (b) processing on a large scale of special categories of data (Article 9) or data relating to criminal convictions; and
- (c) systematic monitoring of a publicly accessible area on a large scale.

AIMVISION's processing meets (a) and (b), and at federation venues likely meets (c). The Egyptian PDPL Article 12 imposes an analogous prior assessment requirement for processing of sensitive data and minors.

### 1.2 Scope
This DPIA covers all AIMVISION-controlled processing:
- Mobile apps (iOS, Android) — Solo, Club, Federation tiers.
- Backend services hosted on Railway (compute) and AWS (storage, queues, KMS).
- ML pipelines (pose detection, classifier inference, LLM-assisted coaching notes).
- Federation on-prem deployments (where physical hardware sits at federation site but logical control remains shared between AIMVISION and federation).
- Marketing case-study processing where personal data leaves the standard service path.

Out of scope: end-user device telemetry collected by Apple/Google as part of OS-level functions; payment-processor-controlled processing (e.g., Stripe is an independent controller for fraud prevention) `[CONFIRM WITH COUNSEL]`.

### 1.3 Controller / processor mapping

| Tier / scenario | AIMVISION role | Other party role | Instrument |
|---|---|---|---|
| Solo subscriber (B2C) | Sole controller | — | Direct ToS + privacy notice |
| Club tier (B2B) | Joint controller `[CONFIRM WITH COUNSEL]` (alternative: AIMVISION as processor for Club) | Club: joint controller | Art. 26 GDPR joint-controller arrangement (template) |
| Federation tier | Joint controller | Federation: joint controller | Art. 26 + PDPL equivalent + Ministry-of-Sport memorandum where applicable |
| Validity studies (academic / clinical research collaborator) | Joint controller for the study | Research institution: joint controller | Research data-sharing agreement + ethics approval |
| Marketing case study | Sole controller (publicity-rights consent only) | — | Separate publicity-rights release |

### 1.4 Sub-processors (initial inventory)

| Processor | Purpose | Data categories | Region | Transfer mechanism |
|---|---|---|---|---|
| Railway | Compute / API hosting | All operational personal data in transit and ephemeral cache | EU (preferred) or US | SCCs (EU→US) `[CONFIRM WITH COUNSEL]`; Egyptian PDPC permit |
| AWS S3 | Object storage (video, audio, derived features) | Video, audio, pose feature blobs | eu-central-1 default; me-south-1 for Egyptian athletes (residency) | SCCs; PDPC cross-border permit |
| AWS KMS | Per-tenant DEK custody | Encryption keys (no personal data) | Same region as data | N/A |
| Sentry | Error telemetry | Stack traces, scrubbed identifiers | EU region required | DPA + SCCs |
| Apple (App Store, HealthKit) | Distribution + optional health-data access | Subscription metadata; health if user opts in | US/EU | Apple DPA + SCCs |
| Google (Play, Health Connect) | Distribution + optional health | Subscription metadata; health if user opts in | US/EU | Google DPA + SCCs |
| Ollama hosting (self-hosted, per-federation) | LLM inference for coaching notes | Pose summaries, anonymized prompts, athlete pseudonyms | Federation region (on-prem or regional cloud) | No external transfer; isolation per federation |
| DeepSeek (model artifact provider) | Model weights only | Pinned hash; no personal data flows out | N/A | Model-license review `[CONFIRM WITH COUNSEL]` |
| Stripe / payment processor | Subscription billing | Name, email, payment metadata | EU/US | Stripe is independent controller for some processing `[CONFIRM WITH COUNSEL]` |
| Email provider (e.g., Postmark, SES) | Transactional mail | Email address, DSAR confirmations | EU region required | DPA + SCCs |
| Whoop / Garmin / wearable APIs (if integrated) | Optional health-data ingest | Heart rate, HRV, sleep | US/EU | User-controlled OAuth + processor DPA |

> **Action:** every processor row above must be backed by a signed DPA before that processor handles personal data. Sprint 1 deliverable.

---

## 2. Description of Processing

### 2.1 Data categories
- **Video** of the athlete in shooting environment. May include face, full body, ambient persons, range/club/federation interior, ambient audio.
- **Audio** captured alongside video (range commands, ambient voices, athlete utterances) plus voluntary **voice notes**.
- **Pose keypoints** (skeletal landmark coordinates per frame) derived from video. Treated as **biometric data** for the purposes of GDPR Art. 9 and PDPL "sensitive data." `[CONFIRM WITH COUNSEL]` on whether sport-form pose qualifies as "biometric data uniquely identifying a natural person" (Art. 4(14)) versus generic motion data — defensive position is to treat as biometric.
- **Voice transcripts** generated from voice notes via on-device or backend ASR. Could embed identifying voice characteristics; transcript text may include health, performance, or identifying content.
- **Performance metrics** (shot timings, group sizes, pose-quality scores, longitudinal trends).
- **Coach annotations** (free text + structured tags) added against athlete sessions.
- **Optional health & wearable data** — HealthKit (iOS), Health Connect (Android), Whoop, Garmin: heart rate, HRV, sleep score, training load. Article 9 health data.
- **Identity & account data** — name, DOB, email, federation ID, club ID, hashed credentials, MFA secrets.
- **Device & technical data** — device ID, app build, OS version, IP address, coarse geolocation, crash stack traces.
- **Consent records** — version, timestamp, granular categories, revocation events.

### 2.2 Volumes (planning estimates, Year 1)
- ~5,000 athletes (Solo + Club + Egypt junior federation).
- ~50,000 sessions captured, average 15 minutes of video each.
- ~750,000 minutes of video (~30 TB raw at 1080p / 30fps).
- ~300 million pose keypoint frames.
- ~10,000 voice notes, ~50,000 LLM-generated coaching summaries.
- ~200 minor athletes (Egypt junior team + other youth programs) — disproportionately weighted in risk treatment.

### 2.3 Frequencies
- Real-time live coaching feed during sessions (sub-100ms inference target on-device).
- Post-session pipeline runs once per session, completes within 15 minutes.
- Longitudinal analytics regenerated nightly.
- ML training (whole-pipeline) runs on cadence of weeks-to-months, only on adult-consented data.
- Marketing case study processing: ad hoc, with separate consent.

### 2.4 Retention (proposed; final values in `data-classification.md` and the published retention schedule)
- Raw video: 90 days default, athlete-extendable to 12 months. Auto-purge thereafter unless legal hold. `[CONFIRM WITH COUNSEL]`
- Pose keypoints (operational): 24 months.
- Pose keypoints (training-eligible, adult-consented only): retained for model lifecycle; subject to crypto-shred on consent revoke.
- Voice notes / transcripts: 12 months.
- Performance metrics & longitudinal trends: lifetime of account + 12 months grace post-deletion request, then crypto-shred.
- Health/wearable data: 12 months.
- Audit logs: 24 months minimum, longer if legal hold or regulatory minimum applies. `[CONFIRM WITH COUNSEL]`
- Marketing assets featuring an athlete: until publicity-rights release expires or revoked.

---

## 3. Article 9 / Special-Category Data Flagging

Three streams trigger Article 9 GDPR (and PDPL Art. 19 sensitive-data) treatment:

1. **Pose keypoints** — defensively treated as **biometric data uniquely identifying a natural person** when combined with athlete account binding. Article 9(2)(a) explicit consent is the primary lawful basis. `[CONFIRM WITH COUNSEL]` on whether sport-pose without face also qualifies; AIMVISION will not rely on that distinction.
2. **Voice notes / audio + transcripts** — voice prints can identify a natural person (CJEU precedent). Treated as biometric where embedded voice characteristics may persist. Speech-to-text transcripts may include health information.
3. **Health and wearable data** — explicit health data under Art. 9. PDPL "sensitive data" (Art. 1).

Additional concerns:
- **Minors' data** is not Article 9 by itself but invokes Art. 8 GDPR (children's information-society services), the UK Children's Code (Standards 1–15), Egypt PDPL minor protections, and US COPPA.
- **Genetic / racial / ethnic / political / religious data** — not within AIMVISION scope; explicitly excluded by data-minimization design.

---

## 4. Necessity & Proportionality Assessment

For each processing purpose: is the processing necessary to achieve the stated purpose, and is it proportionate to that purpose? Alternatives considered and rejected are listed.

### 4.1 Live coaching feed
- **Purpose:** real-time pose-quality feedback to athlete during session.
- **Necessity:** core product utility; without live inference the product is post-hoc only.
- **Proportionality:** on-device inference where possible (no video leaves device); minimum frame rate; no audio used in live feed.
- **Alternatives considered:** post-hoc only (rejected — degrades core value); skeleton-only no-video path (chosen for high-sensitivity contexts where consent is restricted).

### 4.2 Post-session report
- **Purpose:** structured per-shot review with overlays.
- **Necessity:** core product utility.
- **Proportionality:** athlete consents to backend processing; video stored encrypted, lifecycle-purged; report references signed time-range URLs not full re-uploads.

### 4.3 Longitudinal analytics
- **Purpose:** trend detection over weeks/months for the same athlete.
- **Necessity:** stated value proposition.
- **Proportionality:** derived metrics, not raw video, drive analytics; raw video purged on schedule independent of analytics.

### 4.4 ML training
- **Purpose:** improve pose detector and classifiers.
- **Necessity:** product evolution.
- **Proportionality:** **adult-consented data only** by default; minor data excluded unless separate explicit guardian consent; per-sample provenance tracked; erasure requests propagate to exclusion lists for next training run. **Minor opt-in is not the default — it requires affirmative guardian action.**
- **Alternative considered:** only synthetic-data training (rejected as insufficient for performance targets, but partial mitigation).

### 4.5 Marketing case study
- **Purpose:** show AIMVISION's value to prospective customers.
- **Necessity:** commercial; not necessary to deliver the contracted service.
- **Proportionality:** strict separate-consent regime; minors blurred or excluded by default; jurisdiction-specific publicity-rights release required.

### 4.6 Validity / academic studies
- **Purpose:** publish or co-publish on AIMVISION's measurement validity.
- **Necessity:** scientific defensibility, federation procurement support.
- **Proportionality:** opt-in only; ethics-board approval; pseudonymization at minimum, anonymization where feasible.

### 4.7 Security telemetry
- **Purpose:** detect abuse, breach, and fraud.
- **Necessity:** Art. 32 security obligation.
- **Proportionality:** minimum identifying fields; short retention; access restricted to security operations.

---

## 5. Lawful Bases per Data Category per Purpose

Lawful basis is determined per (purpose × data category × subject category). Summary table:

| Purpose | Data category | Subject | Art. 6 basis | Art. 9 basis | Notes |
|---|---|---|---|---|---|
| Account creation | Identity | Adult | Art. 6(1)(b) contract | — | |
| Account creation | Identity | Minor | Art. 6(1)(b) + Art. 8 verifiable parental consent | — | Children's Code applies |
| Live coaching | Pose, video | Adult | 6(1)(b) | 9(2)(a) explicit consent | Granular per-category toggle |
| Live coaching | Pose, video | Minor | 6(1)(b) + parental consent | 9(2)(a) parental consent | |
| Post-session report | Pose, video, audio | Adult | 6(1)(b) | 9(2)(a) | |
| Health-data integration | Wearable / HealthKit | Adult | 6(1)(a) consent | 9(2)(a) | Off by default |
| Health-data integration | Wearable / HealthKit | Minor | parental consent | 9(2)(a) parental consent | Strongly limited |
| ML training | Pose, derived features | Adult | 6(1)(a) consent | 9(2)(a) | Separate toggle |
| ML training | Pose, derived features | Minor | parental consent only if explicitly opted in | 9(2)(a) parental consent | Default = excluded |
| Marketing case study | Likeness, video, name | Adult | 6(1)(a) | 9(2)(a) where biometric | Separate publicity rights |
| Marketing case study | Likeness | Minor | Default excluded | — | Blur or exclude unless extraordinary, jurisdiction-specific guardian release |
| Validity study | Pose, derived features | Any | 6(1)(a) | 9(2)(a) or 9(2)(j) research | Ethics approval mandatory |
| Security telemetry | IP, device ID, audit | Any | 6(1)(f) legitimate interest | — | Balanced against Art. 21 objection |
| Legal/tax records | Identity, billing | Any | 6(1)(c) legal obligation | — | Statutory retention |
| Federation cohort analytics | Aggregated only | Any | 6(1)(b) federation contract + 6(1)(f) | 9(2)(a) + research basis where applicable | k-anonymity threshold required |

`[CONFIRM WITH COUNSEL]` — final basis selection per row, especially the contract/consent split for live coaching, where some authorities prefer consent-only for Art. 9 even where contract is available for Art. 6.

---

## 6. Risks to Data Subjects (Ranked)

Risks are scored on Likelihood × Severity × Subject-Vulnerability. Where minors are subjects, severity floor is High. Each risk maps to mitigations in §7.

### R1. Biometric profiling beyond stated purpose (Severity: Critical)
Pose keypoints could be used to infer non-consented attributes (injury, gait pathology, pregnancy). Mitigation depends on technical and contractual controls forbidding secondary use.

### R2. Performance discrimination by federation, coach, or club (Severity: High)
Longitudinal metrics could be used to deselect athletes from squads or programs in ways athletes did not foresee. Mitigation: strict purpose limitation; athletes have visibility into who consumes their data; export-to-federation requires per-export consent or pre-consented scope.

### R3. Cross-tenant data exposure (Severity: Critical)
Three-tier multi-tenant model with derived per-athlete reports from club captures creates IDOR-class risk. Mitigation: Postgres RLS + application-layer scope filter (per `06-security-engineer.md`).

### R4. Misuse of minor's image in marketing or external publication (Severity: Critical)
Default exclusion of minors from marketing; blur required; separate jurisdiction-valid publicity-rights release required for any minor inclusion.

### R5. Model-derived inferences becoming de facto reputation (Severity: High)
A "pose grade" or "consistency score" computed by AIMVISION may be cited externally and treated as authoritative even if the model is wrong. Mitigation: clear validity disclosures, athlete right to add correction/context, study-grade validity work before federation deployment.

### R6. Sensitive video leak (Severity: Critical)
Range/club-interior video may contain incidental persons, controlled-access facility imagery, or tactically sensitive layouts (federation contexts). Mitigation: encryption at rest + transit; access logging; strict retention; on-prem option for federation.

### R7. Re-identification from pose alone (Severity: Medium-High)
Even without face, pose biomechanics are increasingly identifiable. Mitigation: treat pose as biometric; exclude from publication without consent; aggregation thresholds for cohort analytics.

### R8. LLM prompt-injection or coach-annotation poisoning (Severity: Medium-High)
Free-text coach annotations and voice-note transcripts feed LLM coaching-note generation. Malicious or accidental content could exfiltrate other athletes' data via prompt manipulation. Mitigation: per `06-security-engineer.md` LLM trust-boundary controls.

### R9. Right-to-erasure technically frustrated (Severity: High)
Already-trained model weights cannot exactly unlearn an individual sample. Mitigation: per `right-to-erasure-architecture.md` — sample-provenance tracking, exclusion-list rebuild, tombstone old models, document Art. 17(3)(b) limitation argument with counsel `[CONFIRM WITH COUNSEL]`.

### R10. Health-data-from-wearables creates regulated-context spillover (Severity: High)
Optional HealthKit/Whoop integration brings Art. 9 health data into the system. Mitigation: opt-in only; separate consent; strict retention; never feeds marketing.

### R11. DSAR / erasure request handled poorly (Severity: High)
Failure to fulfill within 30 days (GDPR) or PDPL window. Mitigation: automated DSAR pipeline + Temporal workflow.

### R12. Cross-border-transfer challenge under Schrems II / PDPL (Severity: High)
EU→US flows for Railway, Sentry, etc. require SCCs + Transfer Impact Assessment; Egypt has bidirectional permit obligation. Mitigation: TIA filed with DPIA; permits obtained before first capture in Egypt.

### R13. Federation insider misuse (Severity: High)
Federation admins with access to junior cohort data act outside athlete-disclosed scope. Mitigation: role-bound access; federation-level audit log shipped to federation SIEM; break-glass workflow for support access.

### R14. Discriminatory model performance (Severity: Medium)
Pose detector underperforms on body types, gear, lighting underrepresented in training. Mitigation: validity studies; published model cards; do not rely on AIMVISION pose grades for selection decisions until validated.

### R15. Backup or sub-processor breach (Severity: Critical)
Third-party storage breach exposes raw video and pose data. Mitigation: per-tenant DEKs + crypto-shredding; vendor security review; breach-notification SLAs in DPAs.

---

## 7. Risk Mitigations

Each mitigation references the authoritative spec or ADR. Where the spec does not yet exist, the mitigation is named with the planned spec path.

| Risk | Mitigation | Owner | Reference |
|---|---|---|---|
| R1 | Purpose limitation in privacy notice; technical isolation of analytics from inference; contractual ban on secondary use in joint-controller agreements | Privacy + Legal | `docs/compliance/parental-consent-flow.md`, joint-controller templates |
| R2 | Athlete visibility into recipient list per session; federation export requires explicit scope; audit log of every cross-tier read | Eng + Privacy | `docs/security/audit-logging-spec.md` (planned), `docs/architecture-overview.md` |
| R3 | Postgres RLS + application-layer scope filter; sandboxed derivation worker | Eng | `06-security-engineer.md` §"Multi-Tenant Isolation Recommendation" |
| R4 | Default-exclude minors from marketing; mandatory blur; separate publicity-rights release | Marketing + Legal | `docs/compliance/parental-consent-flow.md` §8 |
| R5 | Validity study before federation procurement; in-product disclaimer on derived scores; athlete right to add commentary | Product + Research | Validity study plan (pending) |
| R6 | KMS-managed encryption at rest; TLS 1.3 in transit; lifecycle purge; on-prem option for federation | Eng | KMS spec (planned), `docs/security/kms-spec.md` |
| R7 | Treat pose as biometric for legal purposes; aggregate-only publication of cohort metrics with k-anonymity | Privacy | `docs/compliance/data-classification.md` |
| R8 | Strip identifiers before prompts; structured prompt format; output validation; per-federation Ollama isolation | Eng + ML | `06-security-engineer.md` §"LLM trust boundary controls" |
| R9 | Sample-provenance tracking; exclusion-list-driven retraining; model tombstoning; per-tenant DEKs for crypto-shredding | Eng + ML | `docs/compliance/right-to-erasure-architecture.md` |
| R10 | Wearable opt-in off by default; separate consent toggle; stricter retention; never feeds marketing | Product + Privacy | `docs/compliance/parental-consent-flow.md` |
| R11 | Temporal-driven erasure pipeline; automated DSAR portal; SLA dashboards; quarterly synthetic-athlete test in CI | Eng | `docs/compliance/right-to-erasure-architecture.md` §8 |
| R12 | SCCs + TIA per processor; PDPC bidirectional permits; data residency for Egyptian athletes (me-south-1 or on-prem) | Legal + Eng | `docs/compliance/egypt-pdpl-action-plan.md` |
| R13 | Per-federation Ollama; KMS root key per federation; audit log shipped to federation SIEM; break-glass workflow | Eng | `06-security-engineer.md` §"Federation on-prem isolation" |
| R14 | Model cards; bias evaluation across body types/gear; validity studies pre-deployment | ML | Model card template (planned) |
| R15 | Per-tenant DEK in KMS; vendor security review; breach-notification SLAs in DPA | Eng + Vendor Mgmt | KMS spec (planned) |

---

## 8. Minor-Protection Assessment

### 8.1 UK Children's Code mapping (Standards 1–15, summary)

| # | Standard | AIMVISION position | Status |
|---|---|---|---|
| 1 | Best interests of the child | Architectural — minors excluded from training and marketing by default | Planned Sprint 3 |
| 2 | Data Protection Impact Assessments | This document | Draft |
| 3 | Age-appropriate application | Branched flows for <13, 13–17, ≥18 | Sprint 3 |
| 4 | Transparency | Plain-language privacy notice + child-readable summary | Sprint 3 |
| 5 | Detrimental use of data | Federation-selection use forbidden by joint-controller agreement; flagged | `[CONFIRM WITH COUNSEL]` |
| 6 | Policies and community standards | Published; tied to enforcement | Sprint 3 |
| 7 | Default settings | High-privacy defaults: ML training off, marketing off, sharing off | Sprint 3 |
| 8 | Data minimisation | On-device inference where possible; minimum data collection | Architecture-baked |
| 9 | Data sharing | No third-party sharing without separate guardian consent | Architecture-baked |
| 10 | Geolocation | Off by default for minors; coarse only if needed for venue attribution | Sprint 3 |
| 11 | Parental controls | Parent account model with read access to child reports | Sprint 3 — see `parental-consent-flow.md` |
| 12 | Profiling | Off by default for minors; ML training opt-in only | Sprint 3 |
| 13 | Nudge techniques | No dark patterns; no engagement-maximizing prompts to minors | Design review gate |
| 14 | Connected toys / devices | GoPro and IMU clearly disclosed; pairing requires parent confirmation for minors | Sprint 7 + |
| 15 | Online tools | DSAR + erasure self-service available to parents | Sprint 17 |

### 8.2 COPPA (US) compliance plan
- DOB collected at signup; users under 13 follow enhanced flow.
- **Verifiable parental consent** under 16 CFR § 312.5: government-ID + signed paper, credit-card-token, signed-PDF with email, or video-verification call. Single-checkbox consent rejected.
- Direct notice to parent before collection.
- Parental access, review, and deletion rights.
- No behavioral advertising to under-13.
- See `parental-consent-flow.md` for implementation.

### 8.3 Egypt PDPL minor + ministerial-consent layer
- Guardian consent under PDPL.
- For federation programs (Egyptian junior team), additional Ministry of Youth and Sports authorization is anticipated `[CONFIRM WITH COUNSEL]` — Egyptian counsel to confirm exact instrument and timing.
- Arabic + English consent forms; lawful-basis text reviewed by Egyptian counsel.

---

## 9. DPO Assessment

A Data Protection Officer **is required** for AIMVISION under GDPR Art. 37(1)(b)–(c) (large-scale special-category processing) and PDPL Art. 8 (sensitive-data processor).

Determinations:
- DPO **must not** be combined with the CTO or any role with direct accountability for processing decisions (conflict of interest under Art. 38(6)).
- DPO must be locally accessible to data subjects and to PDPC (Egyptian regulator). Where AIMVISION lacks an Egyptian establishment, the role can be filled by an external DPO-as-a-service firm with Egyptian presence `[CONFIRM WITH COUNSEL]`.
- EU lead supervisory authority determination is pending — depends on AIMVISION's main establishment in the EU. Italy is plausible if EU operations are based there; otherwise Ireland or another candidate `[CONFIRM WITH COUNSEL]`.
- Appointment target: **Sprint 1**. Appointment deferred until EU/Egyptian counsel confirms scope letter and reporting line to the board.

Reporting line: DPO reports directly to CEO and to a Privacy Committee (CTO, Compliance Lead, Counsel). DPO has unrestricted access to processing activities and the right to escalate to the supervisory authority.

---

## 10. Consultation

### 10.1 Internal consultation
- Affected teams: Engineering, ML, Product, Marketing, Legal, Customer Success, Federation Operations.
- Affected data subjects (representative consultation): athlete advisory panel including at least two parents of junior athletes, two adult athletes, one club coach, one federation coach.
- Workers' council / equivalent: not yet applicable; revisit at EU establishment.

### 10.2 External consultation
- **Egyptian PDPC**: registration + license filing; DPIA submission as part of license dossier.
- **EU lead supervisory authority** (likely Italian Garante or other, `[CONFIRM WITH COUNSEL]`): notification of large-scale special-category processing involving minors.
- **UK ICO**: registration as data controller; Children's Code self-assessment.
- **US FTC posture**: COPPA Safe Harbor program participation under consideration `[CONFIRM WITH COUNSEL]`.

### 10.3 Article 36 prior-consultation triggers
Article 36(1) GDPR requires **prior consultation** with the supervisory authority where the DPIA indicates that processing would result in **high risk** in the absence of mitigations. AIMVISION's residual-risk assessment after mitigations is **medium**, but the following events trigger fresh prior-consultation analysis:
- Adding cross-federation cohort analytics (R2, R7).
- Adding gaze-tracking or eye-biometric capture.
- Adding IMU SKU that captures grip-pressure or heart-rate-from-grip biometrics.
- Any incident in which the operative residual risk is reassessed as high.
- Expansion to a new jurisdiction with stricter rules (e.g., Brazil LGPD ANPD prior consultation for sensitive data of minors `[CONFIRM WITH COUNSEL]`).

---

## 11. DPIA Review Cadence

This DPIA is a living document. Review triggers:
- **Mandatory review at every phase gate** in the AIMVISION sprint plan (gates between phases of the build plan).
- **Mandatory re-assessment on:**
  - Adding the IMU SKU (new biometric stream).
  - Adding gaze tracking or eye biometrics.
  - Adding cross-federation cohort analytics (multiple federations consume same athlete cohort or vice versa).
  - Adding a new sub-processor that touches Article 9 data.
  - Material change in a sub-processor's region or sub-sub-processor list.
  - Any data breach involving Article 9 data.
  - Any supervisory-authority guidance that affects the lawful-basis or risk treatment.
- **Annual review** at minimum, even absent triggers.
- **Version control**: every revision incremented; changelog at end of document; previous versions archived for ≥7 years `[CONFIRM WITH COUNSEL]`.

---

## 12. Sign-Off

| Role | Name | Signature / Date | Notes |
|---|---|---|---|
| DPO | _(pending appointment, Sprint 1)_ | | |
| External EU privacy counsel | _(pending engagement, Sprint 1)_ | | |
| External Egyptian PDPL counsel | _(pending engagement, Sprint 1)_ | | |
| External UK Children's Code counsel | _(pending engagement, Sprint 1)_ | | |
| Compliance Lead | | | |
| CTO | | | |
| CEO | | | |

Sign-off must occur **before Sprint 5 first Egypt capture**. No personal data collection in Egypt before DPIA is signed and PDPC license is in hand.

---

## Changelog
- v0.1 (Sprint 0): initial outline drafted by Compliance Auditor for counsel refinement.

