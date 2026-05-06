# Data Classification — AIMVISION

**Status:** Working draft for counsel refinement.
**Authority:** GDPR Articles 5, 9, 30, 32; Egyptian PDPL (Law 151/2020) Articles 1, 9, 19; UK Children's Code; US COPPA.
**Owner:** DPO + Eng Platform Lead.
**Maintenance:** updated whenever a new data type is introduced; reviewed quarterly.

> Every legal-determination point is tagged `[CONFIRM WITH COUNSEL]`.

---

## Classification scheme

| Class | Definition | Example | Default treatment |
|---|---|---|---|
| **P0 — Critical** | Article 9 / PDPL sensitive; high-impact loss; minor data | Pose keypoints, health, voice biometric, minor's identity | Encrypted under per-tenant DEK; access tightly role-bound; audit log on every read; cross-border restricted; never in marketing without separate consent |
| **P1 — Sensitive** | Personal data with identifying potential and material privacy risk | Account identity, billing identity, device IDs, IP, geolocation | Encrypted under tenant DEK; access role-bound; audit log on writes; cross-border under SCCs/permits |
| **P2 — Internal** | Operational data not direct PII or with very low identifiability | Aggregated cohort metrics, app build numbers, feature flags | Encrypted at rest; standard access controls; aggregate may be shared internally |
| **P3 — Public** | Marketing assets explicitly cleared for publication; product copy; documentation | Approved case study extracts; published model cards | Standard hosting; access for publication; revocation pipeline if subject revokes consent |

**Encryption baseline:** all data at rest is AES-256-GCM under a per-tenant DEK rooted in KMS; all data in transit is TLS 1.3 with certificate pinning on mobile.

**Tenant scope:** every P0/P1 row is tagged with a tenant ID and enforced at Postgres RLS plus an application-layer scope filter. Cross-tenant derivation requires the sandboxed worker pattern documented in `06-security-engineer.md`.

---

## Data-type catalog

> Columns: **Data type | Class | GDPR Art. 9? | PDPL sensitive? | Children's Code applies? | Retention | At-rest encryption | In-transit | Tenant-scoped? | Allowed recipients (RBAC) | Reference**

### Capture data

| # | Data type | Class | Art. 9 | PDPL sens. | Children's Code | Retention | At-rest | In-transit | Tenant-scoped | Allowed recipients | Reference |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Raw session video | P0 | Yes (incidental biometric) `[CONFIRM WITH COUNSEL]` | Yes | Yes (when minor in frame) | 90d default, 12mo athlete-extendable | Tenant DEK | TLS 1.3 | Yes | Athlete (own); coach in scope; sandboxed derivation worker | RP-003 |
| 2 | Raw session audio | P0 | Yes (voice biometric) | Yes | Yes (minor) | 12mo | Tenant DEK | TLS 1.3 | Yes | Athlete (own); coach in scope; ASR pipeline | RP-003, RP-021 |
| 3 | Pose keypoints (live stream) | P0 | Yes (biometric) | Yes | Yes (minor) | Ephemeral; persisted only if session saved | Tenant DEK if persisted | TLS 1.3 | Yes | Athlete device (primary); backend if cloud-inference enabled | RP-004 |
| 4 | Pose keypoints (persisted, operational) | P0 | Yes | Yes | Yes (minor) | 24 months operational | Tenant DEK | TLS 1.3 | Yes | Athlete; coach in scope; analytics worker | RP-005 |
| 5 | Pose keypoints (training-eligible, adult-consented) | P0 | Yes | Yes | N/A (adults only by default) | Model lifecycle; subject to crypto-shred on revoke | Tenant DEK; provenance-tracked | TLS 1.3 | Yes (provenance) | ML pipeline only | RP-008, `right-to-erasure-architecture.md` |
| 6 | Voice notes (audio) | P0 | Yes (voice biometric) | Yes | Yes (minor) | 12mo | Tenant DEK | TLS 1.3 | Yes | Athlete; coach in scope | RP-021 |
| 7 | Voice transcripts | P0 | Yes (derives from biometric; may include health) | Yes | Yes (minor) | 12mo | Tenant DEK | TLS 1.3 | Yes | Athlete; coach in scope; LLM pipeline (anonymized) | RP-021 |
| 8 | Gun IMU stream (future SKU) | P0 | Yes `[CONFIRM WITH COUNSEL]` (could be biometric grip-pressure) | Yes | Yes (minor) | TBD; recommend 24mo | Tenant DEK | TLS 1.3 | Yes | Athlete; coach in scope | DPIA re-assess on add |
| 9 | Health / wearable data (HealthKit, Health Connect, Whoop, Garmin) | P0 | Yes (health) | Yes | Yes (minor — strongly limited) | 12mo | Tenant DEK | TLS 1.3 | Yes | Athlete (own); never marketing | RP-020 |
| 10 | Performance metrics (per session) | P0 | Yes (derives from biometric) | Yes | Yes (minor) | Account lifetime + 12mo grace | Tenant DEK | TLS 1.3 | Yes | Athlete; coach in scope; analytics worker | RP-005 |
| 11 | Longitudinal trends | P0 | Yes (derives from biometric) | Yes | Yes (minor) | Account lifetime + 12mo grace | Tenant DEK | TLS 1.3 | Yes | Athlete; coach in scope | RP-006 |

### Coach and content data

| # | Data type | Class | Art. 9 | PDPL sens. | Children's Code | Retention | At-rest | In-transit | Tenant-scoped | Allowed recipients | Reference |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 12 | Coach annotations | P1 (P0 if discloses health) | Conditional | Conditional | Yes (minor) | Session record + 12mo grace | Tenant DEK | TLS 1.3 | Yes | Athlete; coach team; federation analyst (scoped) | RP-022 |
| 13 | LLM prompts (built from athlete data) | P0 | Yes | Yes | Yes (minor) | 30d quality window then crypto-shred | Tenant DEK; per-federation Ollama isolation | TLS 1.3 | Yes | LLM pipeline; SecOps for incident review | RP-007 |
| 14 | LLM responses (coaching notes) | P0 | Yes | Yes | Yes (minor) | 30d quality window then archived under athlete control | Tenant DEK | TLS 1.3 | Yes | Athlete; coach in scope | RP-007 |
| 15 | Marketing case studies (with consent) | P1 (P3 once athlete approves publication) | Conditional | Conditional | No (minors excluded by default) | Until release expires/revoked | Tenant DEK pre-publish; standard CDN post-publish | TLS 1.3 | Yes pre-publish | Marketing; public post-publish | RP-009, `parental-consent-flow.md` §8 |
| 16 | Federation cohort analytics (aggregated) | P1 (k-anonymity threshold) | No (aggregate) | Conditional | Yes (if minor cohort) | 36mo aggregated | Tenant DEK | TLS 1.3 | Yes | Federation analyst (scoped); AIMVISION federation operations | RP-016 |
| 17 | Validity-study data (pseudonymized) | P0 | Yes | Yes | Yes (rarely; ethics-board only) | Per study protocol | Tenant DEK; restricted-data-sharing portal | TLS 1.3 | Yes | Named research institution under DSA | RP-017 |

### Identity, account, and billing

| # | Data type | Class | Art. 9 | PDPL sens. | Children's Code | Retention | At-rest | In-transit | Tenant-scoped | Allowed recipients | Reference |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 18 | Athlete consent records | P1 | No (metadata only) | No (metadata only) | Yes (records minor consent) | Account lifetime + 7y `[CONFIRM WITH COUNSEL]` | Tenant DEK; append-only hash-chained | TLS 1.3 | Yes | DPO; SecOps; legal on request | RP-023 |
| 19 | DSAR requests | P1 | Conditional (depends on disclosed content) | Conditional | Yes (minors) | 24mo from close | Tenant DEK | TLS 1.3 | Yes | DPO; compliance staff | RP-018 |
| 20 | Erasure requests | P1 | Conditional | Conditional | Yes (minors) | 7y for accountability `[CONFIRM WITH COUNSEL]`; data itself erased | Tenant DEK; pseudonymized | TLS 1.3 | Yes | DPO; eng pipeline | RP-019 |
| 21 | Payment data (tokens; AIMVISION never holds card data) | P1 | No | No | No | 7y tax `[CONFIRM WITH COUNSEL]` | Tenant DEK for tokens; PCI scope at processor | TLS 1.3 | Yes | Finance; payment processor | RP-012 |
| 22 | Authentication credentials (password hashes, MFA secrets) | P1 | No | No | No | Account lifetime | Argon2id hashed; MFA secrets in KMS-backed store | TLS 1.3 | Yes | Auth service; SecOps emergency only | RP-001 |
| 23 | JWT / session tokens | P1 | No | No | No | TTL ≤ 1h; refresh ≤ 30d | Memory-only on backend; iOS Keychain / Android Keystore on device | TLS 1.3 + cert pinning | Yes | Bearer principal | RP-002 |

### Device, environment, and telemetry

| # | Data type | Class | Art. 9 | PDPL sens. | Children's Code | Retention | At-rest | In-transit | Tenant-scoped | Allowed recipients | Reference |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 24 | Device IDs | P1 | No | No | Yes (minor) | Account lifetime | Tenant DEK | TLS 1.3 | Yes | Eng platform; SecOps | RP-024 |
| 25 | IP addresses | P1 | No | No | Yes (minor) | Audit-log retention (24mo) | Tenant DEK | TLS 1.3 | Yes | Eng platform; SecOps | RP-024 |
| 26 | Geolocation (coarse) | P1 | No | No | Yes (minor; off by default) | Session-bound | Tenant DEK | TLS 1.3 | Yes | Eng platform | RP-024 |
| 27 | Geolocation (precise) | P0 (consent-only) | No | No | Yes (minor; never default-on) | Off by default; session-bound when on | Tenant DEK | TLS 1.3 | Yes | Athlete; eng platform | RP-024 |
| 28 | App telemetry (custom events) | P1 | No | No | Yes (minor — minimized) | 90d raw, 13mo aggregated | Tenant DEK | TLS 1.3 | Yes | Eng platform; product analytics | RP-015 |
| 29 | Crash reports / error telemetry (Sentry) | P1 (after PII scrub) | No (post-scrub) | No (post-scrub) | Conditional | 30d raw, 90d aggregated | Sentry-side encrypted; AIMVISION never sees raw before SDK scrub | TLS 1.3 | Conditional | Sentry processor; eng platform | RP-014 |

### Operational, security, and accountability

| # | Data type | Class | Art. 9 | PDPL sens. | Children's Code | Retention | At-rest | In-transit | Tenant-scoped | Allowed recipients | Reference |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 30 | Audit logs (auth, consent, access, admin events) | P1 | No (no Art. 9 payload; references only) | No (references) | Indirectly (records minor events) | 24mo minimum; longer for legal hold | Tenant DEK; append-only hash-chained; write-once bucket | TLS 1.3 | Yes (per-tenant lookup) | DPO; SecOps; federation SIEM for federation events | RP-011 |
| 31 | Federation cohort data (raw, pre-aggregation) | P0 | Yes | Yes | Yes (if minor cohort) | Same as constituent rows (1–11) | Tenant DEK with per-federation root key | TLS 1.3 | Yes | Federation analyst (scoped); audit-logged | RP-016 (constituent data) |
| 32 | QR check-in tokens (PASETO) | P1 | No | No | Yes (when minor) | Redis TTL 90s post-redeem; redemption audit 24mo | KMS-managed signing key | TLS 1.3 | Yes | Athlete (issuance); club (redemption with mTLS or signed assertion) | RP-010, `06-security-engineer.md` |
| 33 | Attribution capabilities (ephemeral derived tokens) | P1 | No | No | Yes (when minor) | Single-use; ≤ session duration | KMS-managed signing key | TLS 1.3 | Yes (purpose-bound) | Club dashboard for attribution-write-only | RP-010 |
| 34 | Marketing publicity-rights release records | P1 | No (metadata) | No (metadata) | Yes (when minor — guardian release) | Until release expires + 7y `[CONFIRM WITH COUNSEL]` | Tenant DEK; append-only | TLS 1.3 | Yes | Marketing (read); legal (read/write); DPO (read) | RP-025 |
| 35 | Model weights and artifacts | P0 (derived from biometric) | Yes (derives) `[CONFIRM WITH COUNSEL]` | Yes (derives) | N/A | Model lifecycle; old versions tombstoned on retire | Tenant-scoped key for federation BYOK; pinned hash | TLS 1.3 | Yes | ML platform; production inference services | `right-to-erasure-architecture.md` §4 |
| 36 | Sample provenance database | P1 | No | No | Yes (minor records) | Lifetime of associated samples + 7y `[CONFIRM WITH COUNSEL]` | Tenant DEK; append-only | TLS 1.3 | Yes | ML platform; DPO | `right-to-erasure-architecture.md` §3 |

---

## Cross-cutting requirements

### Encryption at rest
- All P0 / P1 rows above are encrypted under a per-tenant DEK held in KMS.
- DEK destruction implements crypto-shredding for erasure.
- Federation BYOK option for federation tier.

### Encryption in transit
- TLS 1.3 minimum for all backend traffic.
- Certificate pinning on mobile (with backup pin and remote kill-switch per `06-security-engineer.md`).
- TLS 1.3 also for inter-service traffic in cloud (mTLS where feasible).

### Tenant scoping
- Every P0/P1 row is tagged with `tenant_id` (or composite `(owner_type, owner_id)`).
- Postgres `FORCE ROW LEVEL SECURITY` on every tenant-scoped table.
- Application-layer repository wrapper rejects queries without explicit principal context.
- Both layers must agree (defense-in-depth per `06-security-engineer.md`).

### Cross-border-transfer treatment
- EU→US: SCCs + TIA per processor.
- Egypt-residents: data held in me-south-1 or on-prem; bidirectional PDPC permits required for any cross-border movement.
- Minors: cross-border restricted further; subject to parental consent and ministerial authorization where applicable.

### Children's Code overlay
- Where Children's Code applies, defaults are high-privacy (off / minimal).
- Geolocation off by default for minors.
- Profiling off by default for minors.
- ML training off by default for minors; explicit opt-in via guardian.

### Recipient discipline
- The "Allowed recipients" column is the access-control source of truth for RBAC implementation.
- Every recipient is a role, not a person.
- Federation analyst access is scoped to federation tenant and can be further scoped per cohort.
- Sandbox derivation worker is the only path for cross-tier derivation; it produces narrowly scoped outputs (no full session video into Solo tenant; only attributed frame ranges and aggregate features).

### Audit-log emission rules
- Reads of P0 rows (categories 1–17 above) are audit-logged.
- Writes to P0 and P1 rows are audit-logged.
- Consent grants and revocations are audit-logged with the events specified in `parental-consent-flow.md` §10.
- Audit log retention is 24 months minimum, longer for legal hold.

---

## Decisions pending counsel

The following placeholders are tagged in this document with `[CONFIRM WITH COUNSEL]`:

1. Whether sport-pose without face qualifies as biometric data uniquely identifying a natural person under GDPR Art. 4(14). AIMVISION's defensive position is yes.
2. Exact PDPL sensitive-data scope for IMU streams.
3. Retention windows for billing records, consent records, erasure-request records, and marketing-release records (all currently set to 7 years pending legal review).
4. Marketing-asset takedown SLA on revocation.
5. Crypto-shredding's regulatory acceptability per jurisdiction.
6. Backup-rotation horizon disclosed to athletes (currently 12 months).
7. Article 17(3)(b) limitation argument for already-trained model weights.
8. Whether pose-derived model weights count as personal data themselves.
9. PDPC-specific filing windows (annual report, breach notification timing).
10. Lead supervisory authority in EU.

---

## Changelog
- v0.1 (Sprint 0): initial classification of 36 data types.

