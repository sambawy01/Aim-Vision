# AIMVISION Threat Model and Security Critique

**Reviewer:** Security Engineer · **Date:** 2026-05-06 · **Source:** `AIMVISION_V1_Sprint_Build_Plan.txt` v1.0

## Top 5 Critical Security Gaps

1. **QR check-in scoped token has no specified cryptographic design.** Sprint 16 says "scoped token" and "single-use enforcement" but does not specify token format, claims, binding to consuming club identity, or where scope is enforced. A compromised club dashboard could trivially exfiltrate a Solo user's full history if the token is a bearer JWT with the user's normal `sub`. This is the highest-impact bug in the plan.
2. **Audit logging deferred to Sprint 17.** Auth, consent, scope changes, and data access events that occur in Sprints 3 through 16 will be unauditable retroactively. For minors and biometric data, this is a regulatory failure.
3. **Multi-tenant isolation strategy is undefined.** The plan introduces Solo, Club (Organization), and Federation tiers but never specifies whether isolation is enforced at the database (RLS), ORM, or application layer. Three-tier multi-tenancy with derived cross-tenant reports without an explicit isolation model is the classic IDOR factory.
4. **Minor and biometric data compliance is implied but not designed.** Pose keypoints are GDPR Article 9 special-category biometric data. Egypt Junior team includes minors. The plan mentions "athlete consent flow" once (Sprint 1) and "minor consent handling" once (Sprint 13) with no DPIA, no parental consent flow design, no Egypt Law 151/2020 DPO appointment, no data residency decision, and no right-to-erasure pipeline across video, derived features, and training data.
5. **No threat model, no penetration test, no bug bounty, no SOC 2 path.** Federation procurement will block on these. The Risk Register tracks competitive and execution risk but contains zero security risks.

## QR Check-In Token Design (Specific Recommendation)

Use a **signed opaque token plus server-side single-use ledger**, not a self-contained JWT. Concretely:
- **Format:** PASETO v4.local (XChaCha20 + BLAKE2b) issued by backend with key in KMS. Avoid JWT to eliminate `alg=none` and key-confusion classes.
- **Token body (encrypted claims):** `athlete_id`, `purpose="club_session_attribution_only"`, `iat`, `exp` (90 seconds), `jti` (random 128-bit), `nonce`. No refresh capability, no other scopes.
- **QR payload:** the token plus a 6-digit visible code the athlete reads aloud (channel-binding fallback if QR is photographed).
- **Consumer binding:** the scanning club must present its **mTLS client cert** or signed `club_id` assertion when redeeming. Backend rejects if `redeeming_club_id` is not in the athlete's allowlist (athlete pre-authorizes which clubs may consume their tokens during onboarding at that facility).
- **Replay protection:** Redis-backed `jti` ledger with TTL = `exp + clock_skew`. First redemption marks consumed. Subsequent attempts are logged as security events.
- **Revocation:** athlete can hit "cancel check-in" which writes `jti` to revocation set immediately.
- **Scope enforcement (the critical part):** the redemption response returns a **derived ephemeral session-attribution capability** (separate signed token scoped to one `session_id` and `purpose=attribution_write_only`). The club dashboard never receives the athlete's user token, never receives a token that can read history, and cannot call `/users/{id}/sessions`. Attribution writes go through a dedicated endpoint that only accepts the ephemeral capability.

This means even a fully compromised club dashboard cannot read the Solo user's history.

## Multi-Tenant Isolation Recommendation

- **Postgres Row-Level Security as the floor**, not the ceiling. Every tenant-scoped table gets a `tenant_id` (or composite `(owner_type, owner_id)`) column with `FORCE ROW LEVEL SECURITY` and policies keyed off `current_setting('app.current_principal')` set per-request.
- **Application-layer scope filter as defense-in-depth.** A repository wrapper that refuses queries without an explicit principal context. Both layers must agree.
- **Derived personal report pipeline (the cross-tier risk):** the club session produces frame-level shooter identity attribution from pose tracking + check-in queue position. The derivation job runs in a sandboxed worker that:
  1. Reads the full club session.
  2. Filters frames where `attributed_athlete_id == solo_user_id`.
  3. Writes only those frame ranges, derived shots, and aggregated features to the Solo user's tenant.
  4. **Does not** copy the full session video. The Solo user's report references a signed time-range URL that the storage layer enforces.
  5. Emits an audit record: `frames_attributed`, `frames_excluded`, `attribution_confidence`. Confidence below threshold blocks the report and surfaces a coach review task.
- **Federation on-prem isolation:** each federation gets a separate KMS root key (BYOK option), separate Ollama instance, separate object storage. No shared signing key with cloud. Remote admin requires break-glass approval workflow plus audit log shipped to federation's own SIEM, not back to cloud by default.

## Minor and Biometric Data Compliance (3 Must-Do Items)

1. **DPIA before Sprint 5 (first Egypt capture).** Article 35 GDPR requires a DPIA for systematic biometric processing of minors. Output must list legal basis (explicit consent + contract for adults; parental consent for under-18s), retention periods, recipient list including DeepSeek/Ollama, and Article 9 lawful basis. No data collection until DPIA is signed by counsel.
2. **Parental consent flow with verifiable identity, not a checkbox.** Egypt Law 151/2020 plus GDPR plus US COPPA-equivalents require verifiable parental consent for under-18 (under-13 in COPPA). Implement: separate parent account, government-ID-style verification or signed paper consent uploaded and reviewed, child account linked to parent with parent-controlled deletion, and consent revocation that triggers full erasure within 30 days. Track consent version per data category (video / pose / voice / LLM coaching notes) so future scope expansion requires re-consent.
3. **Right-to-erasure pipeline that actually erases.** Tombstone in DB is not enough. Erasure must propagate to: original video in S3 (delete + lifecycle), derived pose feature vectors, LLM prompt/response logs, training datasets and model checkpoints (track sample provenance with hash-based exclusion lists for the next training run; document that already-trained models cannot unlearn), backups (define crypto-shredding via per-tenant data-encryption keys so destroying the DEK erases the backup data). Egypt data residency: hold Egypt athlete data in-region (AWS me-south-1 or on-prem) and document the transfer impact assessment for any cross-border flow.

## Things Missing From the Plan

1. **Threat model document and STRIDE analysis** — should land in Sprint 2 alongside the architecture document, not be discovered in production.
2. **Audit logging from Sprint 1** — minimum events: auth success/failure, MFA changes, session token issuance, scope changes on annotations, QR token issue/redeem/revoke, cross-tenant data access, consent grant/revoke, admin actions, data export, erasure. Append-only store, integrity-protected (hash-chained or write-once bucket), separate from app DB.
3. **Secrets and key management architecture** — KMS choice (AWS KMS / HashiCorp Vault), per-tenant DEKs, signing key rotation policy, BYOK story for federation, no plaintext secrets in CI, Gitleaks in pre-commit and CI.
4. **Backend rate limiting, DoS protection, and bot defense** — token endpoint, auth endpoint, QR redemption, LLM inference endpoint all need per-principal and global limits. WAF in front of public APIs. Captcha on signup.
5. **Mobile hardening checklist** — JWT in Keychain (kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly) / Android Keystore, never AsyncStorage. TLS pinning with backup pin and remote kill-switch. Certificate transparency check. Jailbreak/root detection as signal not block. Encrypted-at-rest video using iOS Data Protection Class A and Android EncryptedFile. GoPro Wi-Fi: pin GoPro's BSSID + serial after first pairing, warn on mismatch (evil-twin defense). Validate UniFFI/JNI inputs at the boundary, audit `unsafe` blocks in cargo deps with `cargo-audit` and `cargo-deny` in CI.
6. **LLM trust boundary controls** — strip athlete name and direct identifiers before prompts, replace with stable pseudonyms. Treat coach annotations and voice-note transcripts as untrusted input: prompt-injection filter, structured input format, output validation, no tool/function calling from athlete-controlled fields. Log prompts and responses to audit store with redaction. Pin DeepSeek model hash. One Ollama instance per federation with no cross-fed prompt sharing. Document training-provenance limitation: self-hosted Ollama prevents data egress but not pretrained-model leakage of base training data.
7. **SOC 2 Type 1 readiness, penetration test, and responsible-disclosure policy before public launch (Sprint 22 or earlier)** — federations will demand SOC 2 in procurement. Schedule third-party pentest in Sprint 21 (closed beta), publish security.txt and disclosure policy on aimvision.app at launch, stand up a private bug bounty before Sprint 24. Add DSAR self-service tooling (export + delete) in Sprint 17 alongside the audit work, not after launch.
