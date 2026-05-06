# Records of Processing Activities (RoPA) — AIMVISION

**Status:** Working draft for counsel refinement.
**Authority:** GDPR Article 30; PDPL (Law 151/2020) record-keeping requirements; UK DPA 2018.
**Owner:** DPO (once appointed) — Compliance Lead until then.
**Format:** one row per processing activity. Rows are pre-filled for every processing activity AIMVISION will perform at GA. Mark every legal determination with `[CONFIRM WITH COUNSEL]`.
**Maintenance cadence:** updated on every material change to a processing activity; reviewed quarterly by DPO; signed annually by DPO + CTO.
**Storage:** version-controlled in this repo; signed PDF copies in compliance vault; produced on request to supervisory authority within statutory window.

---

## How to read this document

Each processing activity is documented in its own row across the columns specified by Article 30. Where Article 30(1) requires only the controller's view, AIMVISION includes processor-view fields too so this single document satisfies both controller and processor record duties (Art. 30(1) and 30(2)).

**Column legend**

| Column                                           | Description                                                       |
| ------------------------------------------------ | ----------------------------------------------------------------- |
| ID                                               | Stable identifier (e.g., RP-001)                                  |
| Activity                                         | Short name                                                        |
| Purpose                                          | What this processing achieves                                     |
| Lawful basis (Art. 6)                            | One or more of (a)–(f)                                            |
| Special-category basis (Art. 9 / PDPL sensitive) | If applicable                                                     |
| Data categories                                  | The personal data processed                                       |
| Subject categories                               | Who the data is about                                             |
| Recipients                                       | Internal roles + external processors / controllers receiving data |
| Cross-border transfers + safeguard               | Destination + SCCs / adequacy / permit                            |
| Retention                                        | Time bounds + trigger                                             |
| Security measures                                | Pointers to controls                                              |
| Risk level                                       | L / M / H / Critical (post-mitigation)                            |
| Owner                                            | Accountable role                                                  |
| Review date                                      | Last reviewed                                                     |

---

## Processing activity rows

### RP-001 — Account creation

- **Purpose:** create authenticated AIMVISION account; bind to subscription tier.
- **Art. 6:** 6(1)(b) contract.
- **Art. 9:** N/A.
- **Data categories:** name, email, hashed password, DOB, country, federation/club affiliation (optional), MFA secret.
- **Subjects:** adult athletes, coaches, club admins, federation admins, parents (for minor accounts).
- **Recipients:** Engineering on-call (limited), customer support (read-only), email provider (transactional), payment processor (billing identity).
- **Cross-border transfers:** EU→US to email provider (SCCs); Egyptian-resident users' data held in me-south-1 with PDPC permit `[CONFIRM WITH COUNSEL]`.
- **Retention:** lifetime of account + 30 days grace, then crypto-shred. Billing records retained per statutory minimum `[CONFIRM WITH COUNSEL]`.
- **Security:** TLS 1.3, password hashing (Argon2id), MFA, audit log on account-create event.
- **Risk:** Low.
- **Owner:** Eng Platform Lead.
- **Review date:** Sprint 1.

### RP-002 — Authentication

- **Purpose:** log in returning users; issue session credentials.
- **Art. 6:** 6(1)(b).
- **Art. 9:** N/A.
- **Data:** email, password hash check, MFA token, IP, device ID, JWT session.
- **Subjects:** all account-holders.
- **Recipients:** authentication service (Railway), audit-log store.
- **Cross-border:** as RP-001.
- **Retention:** session tokens TTL 1 hour (refresh ≤30 days); auth audit events 24 months minimum.
- **Security:** TLS 1.3, MFA, rate-limit, brute-force lockout, anomaly detection, JWT in iOS Keychain / Android Keystore, certificate pinning.
- **Risk:** Medium (account takeover impact).
- **Owner:** Eng Platform Lead.
- **Review date:** Sprint 1.

### RP-003 — Session capture (live coaching feed)

- **Purpose:** capture athlete shooting session video and pose for live feedback during the session.
- **Art. 6:** 6(1)(b) contract.
- **Art. 9:** 9(2)(a) explicit consent (biometric).
- **Data:** raw video, audio, derived pose keypoints (live), device telemetry.
- **Subjects:** adult athletes; minors with parental consent.
- **Recipients:** athlete's own device (primary); backend ingest (optional, athlete-controlled); coach (in club / federation tier, scoped).
- **Cross-border:** Egyptian athletes processed in me-south-1; otherwise eu-central-1.
- **Retention:** raw video 90 days default, athlete-extendable to 12 months; live pose stream not persisted unless session is saved.
- **Security:** per-tenant DEK, TLS 1.3, signed time-range URLs for replay, RLS scoping, audit log on capture-start.
- **Risk:** High (Article 9 data).
- **Owner:** Eng Capture Lead.
- **Review date:** Sprint 3.

### RP-004 — Live ML inference

- **Purpose:** real-time pose-quality scoring during a session.
- **Art. 6:** 6(1)(b).
- **Art. 9:** 9(2)(a).
- **Data:** pose keypoints, derived shot timing, derived metrics.
- **Subjects:** athletes (adult + minor with consent).
- **Recipients:** on-device inference primarily; backend if athlete enables cloud inference.
- **Cross-border:** none for on-device path; same as RP-003 for cloud path.
- **Retention:** ephemeral for live; persisted as part of session (RP-003) only if session is saved.
- **Security:** model artifact pinned by hash; on-device sandboxing; backend path uses per-tenant DEK + RLS.
- **Risk:** High.
- **Owner:** ML Lead.
- **Review date:** Sprint 4.

### RP-005 — Post-session pipeline

- **Purpose:** generate per-shot review with overlays and metrics.
- **Art. 6:** 6(1)(b).
- **Art. 9:** 9(2)(a).
- **Data:** raw video, pose, audio, voice-note transcripts (if any), derived per-shot features.
- **Subjects:** athletes.
- **Recipients:** athlete (own report); coach (scoped); federation analyst (federation tier only, scoped).
- **Cross-border:** as RP-003.
- **Retention:** report for lifetime of account + 12 months grace; raw video purged on its own schedule.
- **Security:** sandboxed worker; RLS; signed URLs; audit log on derive-and-write.
- **Risk:** High.
- **Owner:** Eng Pipeline Lead.
- **Review date:** Sprint 5.

### RP-006 — Longitudinal analytics

- **Purpose:** trend detection and progress reports per athlete over weeks/months.
- **Art. 6:** 6(1)(b).
- **Art. 9:** 9(2)(a).
- **Data:** derived per-session metrics aggregated over time.
- **Subjects:** athletes.
- **Recipients:** athlete; coach (scoped).
- **Cross-border:** same as RP-003.
- **Retention:** lifetime of account + 12 months grace.
- **Security:** RLS; per-tenant DEK; audit log on aggregate read; no raw video referenced.
- **Risk:** Medium.
- **Owner:** Eng Analytics Lead.
- **Review date:** Sprint 6.

### RP-007 — LLM coaching note generation

- **Purpose:** generate human-readable coaching notes from session metrics.
- **Art. 6:** 6(1)(b).
- **Art. 9:** 9(2)(a) (derives from biometric data).
- **Data:** pose summaries, performance metrics, coach annotations, voice-note transcripts (anonymized).
- **Subjects:** athletes.
- **Recipients:** Ollama instance (per-federation isolation); athlete; coach.
- **Cross-border:** none — Ollama is self-hosted within the relevant region or on-prem.
- **Retention:** prompts and responses retained 30 days for quality, then crypto-shred unless athlete opts to archive.
- **Security:** identifier stripping → pseudonyms; structured-prompt format; output validation; per-federation isolation; pinned model hash.
- **Risk:** High (LLM trust boundary).
- **Owner:** ML Lead.
- **Review date:** Sprint 7.

### RP-008 — ML training (adult-consented data only)

- **Purpose:** train and improve pose detector and classifiers.
- **Art. 6:** 6(1)(a) consent.
- **Art. 9:** 9(2)(a) explicit consent.
- **Data:** pose keypoints + derived features; **never raw video**; **adult-consented only**; minors only if explicit guardian opt-in.
- **Subjects:** consenting adult athletes (default); minors only on explicit opt-in.
- **Recipients:** ML infrastructure (internal); no third-party.
- **Cross-border:** training in eu-central-1 default; Egyptian-consented data optionally trained in me-south-1.
- **Retention:** training-eligible samples retained for model lifecycle; subject to crypto-shred on consent revoke; provenance tracked per sample.
- **Security:** sample-provenance database; consent-version filter at training time; tombstoning on retire; per-tenant DEK; access restricted to ML engineers.
- **Risk:** High (deletion-architecture risk).
- **Owner:** ML Lead.
- **Review date:** Sprint 8.

### RP-009 — Marketing case study

- **Purpose:** feature an athlete or federation in marketing materials.
- **Art. 6:** 6(1)(a) consent + publicity-rights release.
- **Art. 9:** 9(2)(a) explicit consent (where biometric / health features included).
- **Data:** likeness, video, name, performance summary, quotes.
- **Subjects:** **adults only by default**; minors **only** with separate jurisdiction-valid guardian release and federation co-sign where federation-affiliated.
- **Recipients:** marketing channels (web, social, sales decks).
- **Cross-border:** global publication implies multi-jurisdiction processing.
- **Retention:** until release expires or revoked; revoke triggers takedown SLA `[CONFIRM WITH COUNSEL]`.
- **Security:** separate consent record; revocation propagation; minors blurred or excluded; jurisdictional validity check.
- **Risk:** High.
- **Owner:** Marketing + Privacy Lead.
- **Review date:** Sprint 22.

### RP-010 — QR check-in attribution

- **Purpose:** link a Solo athlete's identity to a Club session for personal-report derivation.
- **Art. 6:** 6(1)(b).
- **Art. 9:** 9(2)(a) (because pose-attribution touches biometric).
- **Data:** opaque token (PASETO), athlete pseudonymous ID, club ID, timestamp.
- **Subjects:** Solo athletes consuming Club facilities.
- **Recipients:** Club dashboard receives only an ephemeral attribution-write capability; never the athlete's full token.
- **Cross-border:** same region as athlete.
- **Retention:** token Redis TTL 90 sec post-redeem; redemption audit retained 24 months.
- **Security:** PASETO v4.local; mTLS or signed `club_id`; replay-protection ledger; revocation set; per `06-security-engineer.md`.
- **Risk:** Critical (cross-tenant) — mitigated to Medium by capability-pattern design.
- **Owner:** Eng Platform Lead + Security.
- **Review date:** Sprint 16.

### RP-011 — Audit logging

- **Purpose:** record security and consent events for accountability and breach detection.
- **Art. 6:** 6(1)(c) legal obligation + 6(1)(f) legitimate interest.
- **Art. 9:** N/A (audit log itself does not contain Art. 9 payloads, only references).
- **Data:** principal ID, action, resource, IP, user agent, timestamp, hash of event chain.
- **Subjects:** all users (athletes, coaches, admins, parents).
- **Recipients:** internal SecOps; federation SIEM for federation-tier events.
- **Cross-border:** logs reside with same region as the data they describe; federation logs delivered to federation SIEM.
- **Retention:** 24 months minimum; longer for legal-hold; crypto-shred at end-of-retention.
- **Security:** append-only / hash-chained; write-once bucket; tamper-evident; integrity check on read.
- **Risk:** Medium.
- **Owner:** SecOps Lead.
- **Review date:** Sprint 8 (audit logging live).

### RP-012 — Payment processing

- **Purpose:** collect and reconcile subscription payments.
- **Art. 6:** 6(1)(b) + 6(1)(c) for tax records.
- **Art. 9:** N/A.
- **Data:** name, email, billing address, payment-method token (no PAN at AIMVISION), invoice history.
- **Subjects:** subscribers (adults; minors not direct subscribers — parent pays).
- **Recipients:** Stripe (or equivalent) — PCI-DSS scope segregation; AIMVISION never holds card data.
- **Cross-border:** Stripe operates EU + US; SCCs in place via Stripe DPA `[CONFIRM WITH COUNSEL]`.
- **Retention:** 7 years for tax records `[CONFIRM WITH COUNSEL]`.
- **Security:** payment processor handles PCI scope; AIMVISION holds reference tokens only; access restricted.
- **Risk:** Low (segregated scope).
- **Owner:** Finance + Eng Platform.
- **Review date:** Sprint 4.

### RP-013 — Customer support

- **Purpose:** respond to user-initiated support requests.
- **Art. 6:** 6(1)(b) + 6(1)(f).
- **Art. 9:** 9(2)(a) where ticket discloses biometric/health context.
- **Data:** ticket content, conversation history, screenshots provided by user, account context.
- **Subjects:** account-holders + parents for minor accounts.
- **Recipients:** support staff (role-bound); helpdesk vendor (if used) under DPA.
- **Cross-border:** depends on helpdesk vendor location; EU-region preferred.
- **Retention:** 24 months from ticket close.
- **Security:** access role-bound; audit log on support reads; redaction at ingest.
- **Risk:** Medium.
- **Owner:** Customer Success Lead.
- **Review date:** Sprint 8.

### RP-014 — Error telemetry

- **Purpose:** detect and diagnose application errors.
- **Art. 6:** 6(1)(f).
- **Art. 9:** N/A (athlete identifiers stripped before send).
- **Data:** stack trace, app version, OS, scrubbed identifiers, breadcrumbs.
- **Subjects:** all app users.
- **Recipients:** Sentry (EU region).
- **Cross-border:** EU only by config.
- **Retention:** 30 days raw, 90 days aggregated.
- **Security:** PII scrubbing at SDK; Sentry DPA + SCCs; access role-bound.
- **Risk:** Low.
- **Owner:** Eng Platform.
- **Review date:** Sprint 2.

### RP-015 — Performance telemetry

- **Purpose:** monitor latency, error rates, capacity.
- **Art. 6:** 6(1)(f).
- **Art. 9:** N/A.
- **Data:** request/response timings, principal ID hashed, route, status.
- **Subjects:** all users.
- **Recipients:** Eng + SRE.
- **Cross-border:** same region as service.
- **Retention:** 90 days raw, 13 months aggregated.
- **Security:** hashed identifiers; access role-bound.
- **Risk:** Low.
- **Owner:** SRE Lead.
- **Review date:** Sprint 2.

### RP-016 — Federation cohort analytics

- **Purpose:** federation-level performance and program-improvement analytics.
- **Art. 6:** 6(1)(b) joint-controller contract + 6(1)(f) where research framing applies.
- **Art. 9:** 9(2)(a) consent + 9(2)(j) research where ethics framework applies.
- **Data:** aggregated metrics per cohort; **k-anonymity threshold enforced** before display.
- **Subjects:** athletes within federation cohort.
- **Recipients:** federation analyst (scoped); AIMVISION federation operations.
- **Cross-border:** federation region.
- **Retention:** 36 months aggregated; per-athlete aggregate excluded if athlete erased.
- **Security:** k-anonymity threshold; RLS; signed export; audit log on cohort read.
- **Risk:** Medium-High (re-identification risk).
- **Owner:** Federation Operations + Privacy.
- **Review date:** Sprint 12.

### RP-017 — Validity-study data sharing

- **Purpose:** support academic / clinical validity studies of AIMVISION measurements.
- **Art. 6:** 6(1)(a) consent + collaborator's research basis.
- **Art. 9:** 9(2)(j) research with appropriate safeguards `[CONFIRM WITH COUNSEL]` + 9(2)(a) consent.
- **Data:** pseudonymized pose features; derived metrics; rarely raw video (case-by-case ethics-approved).
- **Subjects:** consenting adult athletes; minors only if guardian + ethics-board approve.
- **Recipients:** named research institution under data-sharing agreement.
- **Cross-border:** depends on research institution; SCCs and TIA per case.
- **Retention:** per study protocol; deletion at study close unless preservation required by ethics.
- **Security:** pseudonymization; restricted-data-sharing portal; audit log; ethics-board oversight.
- **Risk:** High.
- **Owner:** Research Lead + Privacy.
- **Review date:** Sprint 18.

### RP-018 — DSAR fulfillment

- **Purpose:** respond to subject access, rectification, portability, objection requests.
- **Art. 6:** 6(1)(c) legal obligation.
- **Art. 9:** as applicable to data being disclosed.
- **Data:** all categories the subject is entitled to see/export.
- **Subjects:** any data subject; minors via parent.
- **Recipients:** the data subject themselves; identity-verification provider.
- **Cross-border:** delivery to the subject in the subject's country.
- **Retention:** DSAR ticket + correspondence retained 24 months.
- **Security:** identity verification; secure-download link; audit log of disclosure.
- **Risk:** Medium.
- **Owner:** DPO.
- **Review date:** Sprint 17.

### RP-019 — Erasure pipeline

- **Purpose:** fulfill right-to-erasure across all systems including training datasets and model weights to the extent technically feasible.
- **Art. 6:** 6(1)(c).
- **Art. 9:** as applicable.
- **Data:** all data on the subject across DBs, S3, derived feature stores, training datasets, audit log (subject to legal-hold), backups, federation on-prem instances.
- **Subjects:** any data subject; minors via parent; athletes turning 18 via auto-prompt.
- **Recipients:** internal pipeline; federation on-prem (relayed via authenticated channel).
- **Cross-border:** erasure executes in the region of origin; federation acks completion.
- **Retention:** erasure-request ticket retained 7 years for accountability `[CONFIRM WITH COUNSEL]`; erased data is gone.
- **Security:** Temporal workflow; per-tenant DEK crypto-shredding; sample-provenance exclusion list; audit log; quarterly synthetic-athlete CI test.
- **Risk:** Critical (architecture pre-mitigation; reduced to High post-mitigation given pre-erasure model-weight limitation `[CONFIRM WITH COUNSEL]`).
- **Owner:** Eng Platform + DPO.
- **Review date:** Sprint 17.

### RP-020 — Wearable data ingest (HealthKit / Health Connect / Whoop / Garmin)

- **Purpose:** ingest opt-in wearable health data for richer coaching insights.
- **Art. 6:** 6(1)(a) consent.
- **Art. 9:** 9(2)(a) explicit consent (health data).
- **Data:** heart rate, HRV, sleep, training load.
- **Subjects:** adults who explicitly opt in; minors only with explicit parental consent and strong default-off.
- **Recipients:** AIMVISION backend; never marketing; never federation export without separate consent.
- **Cross-border:** same as athlete's primary region.
- **Retention:** 12 months unless athlete explicitly extends.
- **Security:** OAuth scopes minimal; per-tenant DEK; access role-bound; revocable in app.
- **Risk:** High.
- **Owner:** Product + Privacy.
- **Review date:** Sprint 10.

### RP-021 — Voice notes and transcripts

- **Purpose:** allow athletes/coaches to record voice notes attached to sessions; transcribe for searchability and LLM input.
- **Art. 6:** 6(1)(b).
- **Art. 9:** 9(2)(a) (voice as biometric; transcript may include health).
- **Data:** audio, ASR transcript.
- **Subjects:** athletes, coaches.
- **Recipients:** athlete; coach in scope; LLM pipeline (anonymized).
- **Cross-border:** same as athlete's region.
- **Retention:** 12 months.
- **Security:** per-tenant DEK; redaction filter before LLM use; audit log.
- **Risk:** High.
- **Owner:** Product + ML.
- **Review date:** Sprint 9.

### RP-022 — Coach annotations

- **Purpose:** coaches add structured + free-text annotations on sessions.
- **Art. 6:** 6(1)(b) (coach-as-data-subject for the annotation authorship; athlete-as-subject for content).
- **Art. 9:** as applicable to content.
- **Data:** free text, structured tags, time codes, author identity.
- **Subjects:** athletes (subject of annotation); coaches (author).
- **Recipients:** athlete; coach team; federation analyst (scoped).
- **Cross-border:** same region.
- **Retention:** lifetime of session record + 12 months grace.
- **Security:** RLS; LLM trust-boundary controls when annotations feed prompts.
- **Risk:** Medium.
- **Owner:** Product + Eng.
- **Review date:** Sprint 7.

### RP-023 — Athlete consent records

- **Purpose:** record granular consent grants and revocations per data category × purpose × version.
- **Art. 6:** 6(1)(c) legal obligation.
- **Art. 9:** stores metadata about Art. 9 consent; not Art. 9 itself.
- **Data:** subject ID, category, purpose, consent version, timestamp, IP, evidence pointer (e.g., signed PDF for parental consent).
- **Subjects:** all data subjects.
- **Recipients:** DPO; SecOps; legal on request.
- **Cross-border:** same region as subject.
- **Retention:** lifetime of account + 7 years post-erasure for accountability `[CONFIRM WITH COUNSEL]`.
- **Security:** append-only, hash-chained; tamper-evident; access role-bound.
- **Risk:** Medium.
- **Owner:** DPO + Eng.
- **Review date:** Sprint 3.

### RP-024 — Device IDs, IP addresses, geolocation, app telemetry

- **Purpose:** support session, attribution, security telemetry.
- **Art. 6:** 6(1)(b) for session; 6(1)(f) for security; 6(1)(a) for precise geolocation (off by default for minors).
- **Art. 9:** N/A.
- **Data:** device ID, IP, coarse geolocation (region), precise geolocation (only on opt-in), app build, session events.
- **Subjects:** all users.
- **Recipients:** internal infra.
- **Cross-border:** same region.
- **Retention:** session-bound + audit log retention.
- **Security:** TLS; access role-bound; minimization.
- **Risk:** Low-Medium.
- **Owner:** Eng Platform.
- **Review date:** Sprint 2.

### RP-025 — Marketing publicity-rights release records

- **Purpose:** track who has signed a publicity-rights release and the scope.
- **Art. 6:** 6(1)(c) recordkeeping.
- **Art. 9:** stores metadata about release scope.
- **Data:** release scope, jurisdictions, expiry, revocation events, signed-document pointer.
- **Subjects:** athletes who have given a release.
- **Recipients:** Marketing (read), Legal (read/write), DPO (read).
- **Cross-border:** as needed for marketing publication.
- **Retention:** until release expires + 7 years `[CONFIRM WITH COUNSEL]`.
- **Security:** append-only; access role-bound; revocation triggers takedown workflow.
- **Risk:** Medium.
- **Owner:** Marketing + Legal.
- **Review date:** Sprint 22.

---

## Annual sign-off

| Role            | Name | Date | Signature |
| --------------- | ---- | ---- | --------- |
| DPO             |      |      |           |
| CTO             |      |      |           |
| Compliance Lead |      |      |           |

## Changelog

- v0.1 (Sprint 0): pre-fill of all 25 anticipated processing activities for counsel review.
