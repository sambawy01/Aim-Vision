# Right-to-Erasure Architecture — AIMVISION

**Status:** Working draft for counsel refinement.
**Authority:** GDPR Article 17, Article 17(3) limitations; Egyptian PDPL erasure right; UK Children's Code Standard 15; US COPPA parental deletion right.
**Owner:** Eng Platform Lead + DPO (once appointed).
**Engineering reference:** complements `06-security-engineer.md` and `dpia-outline.md`.

> Every legal-determination point is tagged `[CONFIRM WITH COUNSEL]`. Architectural decisions that are independent of law are stated authoritatively.

---

## 1. Why architectural, not procedural

A right-to-erasure program that ends at "we deleted the row" fails for AIMVISION because:

1. **Pose keypoints train models.** Once a sample contributes to model weights, the resulting weights are a derivative work of that sample. Deleting the original sample does not unlearn it. Model weights cannot be exactly retracted from existing parameters without retraining.
2. **Backups and replicas.** Deleting from primary storage is meaningless if backups retain the data; auditors will look at backup retention and exposure.
3. **Sub-processor stores.** Sentry traces, LLM prompts, transcoder caches, CDN objects all hold personal data references after deletion.
4. **Federation on-prem instances.** Data lives in places AIMVISION does not own.
5. **Audit logs and legal-hold corpus.** These cannot be erased without breaking accountability; carve-outs must be documented and bounded.

The only defensible posture is to make erasure an architectural property of the system, not a procedural promise. That property has three pillars:

- **Per-tenant cryptographic isolation** so destroying a key destroys access to data, including in backups.
- **Sample provenance tracking** so training pipelines can reconstruct without erased samples and old models can be tombstoned.
- **An automated erasure workflow** that fans out across all storage layers and produces evidence of completion.

This document specifies all three.

---

## 2. Per-tenant Data Encryption Keys (DEK)

### 2.1 Concept

Every tenant (Solo athlete, Club, Federation) is assigned a unique **Data Encryption Key (DEK)**. All tenant data at rest is encrypted under the tenant's DEK. DEKs are themselves encrypted by a per-region **Key Encryption Key (KEK)** rooted in AWS KMS (or HashiCorp Vault for self-hosted federation).

### 2.2 Storage

- KMS holds the master KEK in HSM-backed regions.
- DEKs are wrapped with the KEK; wrapped form is stored alongside metadata in the operational DB.
- Plaintext DEK is materialized in process memory only at decrypt time; never persisted plaintext.
- Per-tenant rotation cadence: 12 months default; immediate on suspicion of compromise.

### 2.3 Crypto-shredding

**Destroying the DEK destroys the data.** This is the load-bearing property:

- All copies of tenant data on primary storage, replicas, snapshots, and **backups** are encrypted under the tenant's DEK.
- When erasure is finalized, the wrapped DEK is deleted from KMS and from all metadata stores.
- Backup-tape or backup-bucket entries cannot be decrypted thereafter.
- Operationally indistinguishable from physical deletion for audit-purposes provided that no prior plaintext copy escaped (audit log of decrypts mitigates this).

`[CONFIRM WITH COUNSEL]` — the regulatory acceptability of crypto-shredding for "erasure" varies by jurisdiction. Most EU DPAs accept it; some US state regulators expect physical purge in addition. AIMVISION's posture is crypto-shred + best-effort physical purge on the next backup-rotation cycle.

### 2.4 Granularity options

Two implementation tiers:

- **Tenant-level DEK (default).** Simpler. Single DEK per tenant. Adequate for Solo and Club tiers where erasure-of-tenant means erasure-of-account.
- **Sub-tenant per-record encryption keys.** For federation tier where individual athlete erasure within a federation cohort is required without affecting the cohort. Each athlete has a sub-DEK; tenant DEK is hierarchical.

### 2.5 Key custody for federation on-prem

- Federation has BYOK option: federation supplies its own KMS root key.
- AIMVISION cloud cannot decrypt federation on-prem data without federation cooperation.
- Federation's erasure pipeline mirrors the cloud pipeline; AIMVISION cloud receives an authenticated ack of completion and never the data itself.

---

## 3. Sample provenance tracking

### 3.1 The provenance record

Every sample that enters a training pipeline carries a provenance record:

```
sample_id        — opaque ID
athlete_id       — pseudonymous ID linked to the data subject
consent_version  — version of consent at the time the sample was eligible
ml_training_consent_bool — was ML-training consent active?
data_categories  — which categories this sample touches (pose, audio, etc.)
collected_at     — capture timestamp
ingested_at      — pipeline ingest timestamp
source           — which RoPA activity produced it
```

Provenance is stored in a dedicated provenance database, separate from the feature store. Read-only to training jobs.

### 3.2 Training-time enforcement

Every training run filters by:

- `ml_training_consent_bool = TRUE` at training time.
- Athlete not on the **per-model exclusion list** (next subsection).
- Consent version still valid (not expired by re-consent cadence).

Filtering happens at the data-loader; no exclusion-aware behavior is needed inside the training loop. A test harness verifies that the data-loader correctly excludes a synthetic-athlete present in fixtures.

### 3.3 Per-model exclusion list

Each trained model has an immutable exclusion list — the set of `athlete_id` whose samples must be excluded from any retraining.

When an erasure request is fulfilled:

1. Athlete is added to the exclusion list of every active model.
2. Next training run for that model produces a new version that has not seen this athlete's samples.
3. Old model version is marked for retirement (see §4).

The exclusion list itself contains pseudonymous IDs only; no Article 9 data.

---

## 4. Already-trained model unlearning

### 4.1 The intractable problem

**Exact unlearning** — producing a model identical to one that was never trained on the erased sample — is computationally infeasible for production-scale models without full retraining. AIMVISION will not promise exact unlearning.

### 4.2 The Article 17(3)(b) limitation argument

GDPR Article 17(3) provides that the right to erasure does not apply where processing is necessary for compliance with a legal obligation, for public-interest tasks, for archiving / scientific research, or for the establishment, exercise, or defence of legal claims. Article 17(3)(b) does **not** directly cover model weights, but the right's practical limits in the face of derivative works are an active area of regulator commentary `[CONFIRM WITH COUNSEL]`.

AIMVISION's documented position, subject to counsel review:

- Erasure of the **source data** is fully effected.
- Erasure from already-trained model weights is **not technically feasible by exact unlearning**.
- AIMVISION offers, in lieu, the §4.3 / §4.4 mitigations.
- The position is disclosed to athletes at consent; consent specifically acknowledges the model-weight limitation.
- The position is reviewed with counsel at every DPIA review cycle and on any regulator communication on the topic.

### 4.3 Tombstone + retire on next retrain

- The affected model is marked **deprecated** in the model registry the moment exclusion-list entry is added.
- Production traffic is migrated to the next-version model (built without the erased samples) within an SLA `[CONFIRM WITH COUNSEL]` of 90 days for major models, 30 days for high-frequency-retrain models.
- Old model artifacts are removed from registry once no production traffic depends on them; a record of retirement is kept in the audit log.

### 4.4 Approximate unlearning (research-grade, not production)

Techniques such as **SISA training** (sharded, isolated, sliced, aggregated), **influence-function-based unlearning**, and **membership-inference defenses** can reduce the degree to which a sample influences model weights without full retraining. AIMVISION's posture:

- These are explicitly research-grade. They are not used as the primary erasure mechanism.
- Where SISA-style architectures align with model design (e.g., per-cohort sub-models), they may be adopted as a defense-in-depth measure.
- Publicly disclosed model cards describe the unlearning posture honestly.

---

## 5. Erasure pipeline (Temporal workflow)

The pipeline is implemented as a **Temporal workflow** to give durable, replayable, auditable execution. The user-facing trigger is the DSAR portal (Sprint 17); the pipeline is also invoked by the auto-purge automation for athletes who turn 18 without re-consent (per `parental-consent-flow.md` §7).

### 5.1 Workflow definition (logical)

```
Erasure(athlete_id, requested_by, reason) {
    Step 1: Receive request
    Step 2: Validate identity + 30-day grace period
    Step 3: Enumerate references
    Step 4: Tombstone records + crypto-shred queued
    Step 5: Emit completion confirmation
    Step 6: Trigger model retraining (if threshold reached)
}
```

### 5.2 Step 1 — receive request

Sources of erasure requests:

- Athlete via DSAR self-service portal (Sprint 17).
- Parent / guardian via parent account (per `parental-consent-flow.md`).
- Auto-prompt at majority transition (Day 90 without re-consent).
- Admin-initiated on behalf of a data subject (compliance staff, with audit trail).
- Federation-mediated channel (federation forwards an erasure request from an enrolled athlete).

Each request gets an `erasure_ticket_id` and is recorded in the erasure-ledger (append-only, retained for accountability).

### 5.3 Step 2 — validate identity + grace period

- **Identity verification** — DSAR portal requires re-authentication + secondary factor; admin-initiated requires documented data-subject signature.
- **Grace period** — 30 days default per GDPR practical-rights guidance and per Egyptian PDPL `[CONFIRM WITH COUNSEL]`. During grace:
  - Account is placed in "pending erasure" mode; no new processing initiated.
  - Athlete may revoke the request without penalty.
  - Notifications sent to athlete, parent (if applicable), federation (if applicable).
- After grace, workflow advances to Step 3.

### 5.4 Step 3 — enumerate all references

The workflow performs an exhaustive inventory of references to the data subject across:

| Layer                                 | Data                                                            | Action                                                                                                                             |
| ------------------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Operational DB                        | Account, session metadata, consent records, performance metrics | Tombstone + crypto-shred at end of grace                                                                                           |
| S3 video store                        | Raw video files                                                 | Object-version delete + lifecycle purge; per-tenant DEK destroyed                                                                  |
| Derived feature store                 | Pose feature blobs, longitudinal metric series                  | Tombstone + crypto-shred                                                                                                           |
| Training datasets                     | Pose samples in adult-consented training corpus                 | Add to exclusion list; physical removal from current dataset version; old dataset versions tombstoned                              |
| Audit log                             | Auth, consent, access events                                    | **Retained** per legal hold + retention schedule; subject's identifiers replaced with pseudonyms in any non-essential audit fields |
| Erasure-ledger                        | Record of this and prior requests                               | Retained per accountability obligation; pseudonymized                                                                              |
| LLM prompt / response logs            | Coaching-note prompts referencing this athlete                  | Tombstone + crypto-shred; per-federation Ollama logs purged                                                                        |
| Backups                               | All above categories in encrypted backups                       | Crypto-shred via DEK destruction; physical purge on next rotation                                                                  |
| Federation on-prem instances          | Data held at federation site                                    | Erasure request relayed; federation acks completion                                                                                |
| Sub-processor stores (Sentry, Stripe) | Scrubbed identifiers, billing records                           | Sub-processor erasure API + signed confirmation; billing records retained for tax minimum then erased                              |
| Marketing assets                      | Likeness in published materials                                 | Takedown SLA; revocation of publicity-rights release                                                                               |

### 5.5 Step 4 — tombstone + crypto-shred

- Records are marked tombstoned in operational DB (referential integrity preserved; identifiers redacted to pseudonyms).
- Per-record sub-DEKs are destroyed where granular tier is in use.
- Otherwise, tenant DEK is queued for destruction at end of grace period.
- KMS receives delete-DEK call; deletion is irreversible and logged.

### 5.6 Step 5 — completion confirmation

- Each step emits an audit event.
- A signed completion certificate is generated for the athlete: lists categories erased, sub-processors notified, model exclusion-list updates, residual data per legal hold, model-weight limitation statement.
- Certificate delivered via the DSAR portal and emailed to the athlete + parent.
- Erasure-ledger entry closed.

### 5.7 Step 6 — model retraining trigger

- A counter tracks pending exclusion-list additions per active model.
- Threshold-driven retrain: e.g., on first exclusion or every N exclusions, schedule retrain.
- Retrained model promoted to production within SLA; old model retired per §4.3.

### 5.8 Failure modes and retries

- Each step is idempotent; Temporal retries on failure with exponential backoff.
- Hard failures (e.g., sub-processor refuses erasure) escalate to DPO via on-call ticket.
- Workflow is replayable for audit reconstruction.

---

## 6. Backup retention

### 6.1 Backup design

- Backups are encrypted under the tenant DEK; DEK destruction renders backups unreadable.
- Backup rotation: 90 days operational backups; 12 months disaster-recovery (DR) snapshots.
- DR snapshots are subject to legal-hold rules; data subjects are informed that DR snapshots holding their data are unreadable after DEK destruction but may persist on physical media until the next rotation.

### 6.2 DEK rotation interaction

- Per-tenant DEK rotation rotates the data-encryption key without re-encrypting the existing data set (existing data stays under the previous key version; new data uses the new version).
- On erasure, **all key versions** for the tenant are destroyed.
- This makes backup data automatically inaccessible at a known horizon: the operational-backup window for new data, the DR window for older data.

### 6.3 Documented horizon

- Athletes are told: "Some encrypted backup copies of your data may persist on physical media for up to 12 months after your erasure request, but they are unreadable because the encryption key has been destroyed."

`[CONFIRM WITH COUNSEL]` — language and exact horizon to be reviewed.

---

## 7. Federation on-prem

Federation deployments hold data on hardware AIMVISION does not own. Erasure architecture there:

- AIMVISION software running on federation hardware exposes the same erasure workflow as the cloud.
- Erasure requests originating in cloud are relayed to federation via authenticated control channel.
- Federation runs the workflow locally; data never leaves federation premises during erasure.
- Federation acks completion to cloud; ack is recorded in cloud audit log.
- Crypto-shredding uses federation's own KMS (BYOK).
- Federation joint-controller agreement obligates the federation to honor erasure requests routed via AIMVISION.

For Egypt junior team specifically, the federation acknowledgement also goes to the cloud audit log so AIMVISION can demonstrate cross-organization accountability to PDPC.

---

## 8. Test plan

Erasure correctness is verified by **CI-driven synthetic-athlete tests** every quarter (and on every change to the erasure pipeline).

### 8.1 Synthetic athlete lifecycle

1. Test harness creates a synthetic athlete `synthetic-athlete-{quarter}`.
2. Synthetic athlete signs up, grants full consent including ML-training and marketing.
3. Harness simulates: 5 sessions captured, full pipeline run (raw video, pose, derived features, longitudinal metrics, LLM coaching note generation).
4. Harness simulates: synthetic samples flow into the next training-dataset snapshot.
5. Harness simulates: synthetic athlete featured in a synthetic marketing case study artifact.
6. Erasure request submitted via DSAR endpoint.
7. Workflow runs to completion (grace period collapsed for tests).
8. **Verification asserts:**
   - No record of synthetic athlete in operational DB (except tombstone identifiers).
   - S3 objects gone or DEK-shredded.
   - Derived feature store empty for that ID.
   - Training-dataset snapshot's next build excludes the synthetic athlete (provenance check).
   - Old model marked deprecated; new model trained without samples.
   - Audit log retains pseudonymized references only.
   - LLM prompt logs purged.
   - Backups encrypted with destroyed DEK; decrypt attempt fails.
   - Marketing asset takedown record exists.
   - Completion certificate generated.

### 8.2 Fail-loud expectations

- Any deviation from expected end-state fails CI; release is blocked.
- A red-team variant adds adversarial conditions (concurrent re-signup attempts, partial sub-processor failure).

### 8.3 Annual external attestation

- Once SOC 2 program is mature (Sprint 18+), an external auditor performs the synthetic-athlete test as part of the engagement and produces evidence in the audit report.

---

## 9. Limitations and disclosures

What we tell athletes (and parents) at consent and at erasure:

- **Source data is erased.** Your videos, audio, pose data, voice notes, performance metrics, and coaching notes are erased from AIMVISION systems.
- **Models already trained may have learned from your data.** We cannot exactly unlearn it. We retire affected models on the next retrain cycle and the next-version model is built without your data.
- **Backups become unreadable, not necessarily physically purged.** Encrypted backups persist on physical media for up to 12 months after erasure; the encryption key has been destroyed so the data is inaccessible.
- **Audit logs are retained.** Some operational metadata (e.g., that an account existed and was erased) is retained in pseudonymized form for legal accountability.
- **Marketing assets are taken down within 30 days** of revocation `[CONFIRM WITH COUNSEL]`.
- **Federation on-prem deployments** run the same erasure workflow; AIMVISION receives an authenticated confirmation from the federation.

These statements are surfaced:

- At initial consent (acknowledged in the consent record).
- At erasure-request submission (acknowledged before submission).
- In the privacy notice, in plain language.
- At every consent-version change.

Consent records pin the specific language version the athlete saw, so subsequent versions do not retroactively change what was disclosed.

---

## 10. Documentation and ADR linkage

- **ADR-XXX (planned)**: Per-tenant DEK and crypto-shredding for erasure.
- **ADR-XXX (planned)**: Sample provenance tracking and exclusion-list-driven retraining.
- **ADR-XXX (planned)**: Temporal-driven erasure workflow.
- **`docs/security/audit-logging-spec.md` (planned)**: Audit-log fields and retention.
- **`docs/security/kms-spec.md` (planned)**: KMS architecture, key hierarchy, rotation, BYOK.
- **`docs/compliance/parental-consent-flow.md`**: Majority-transition auto-purge.
- **`docs/compliance/dpia-outline.md`**: Risk R9 (right-to-erasure architecture risk) mitigations.
- **`docs/compliance/egypt-pdpl-action-plan.md`**: Federation on-prem flow, PDPL erasure-right satisfaction.

---

## Changelog

- v0.1 (Sprint 0): initial architecture drafted.
