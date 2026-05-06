# AIMVISION Audit Logging Specification

**Owner:** Security Engineer + Backend Lead
**Status:** Draft v1.0 — must be live from Sprint 1, not deferred to Sprint 17
**Source review:** `docs/reviews/06-security-engineer.md` §"Things Missing From the Plan" #2
**Related:** `docs/security/threat-model.md`, `docs/security/qr-checkin-token-spec.md`, `docs/security/multi-tenant-isolation.md`, `docs/reviews/07-compliance-auditor.md`

---

## 1. Why Audit From Sprint 1

The original plan defers audit logging to Sprint 17. That is a regulatory failure for AIMVISION specifically because:

- **Minor athletes.** Egypt junior team, EU youth squads. Any processing of minor data must be retroactively explicable. Sprint 1 builds the auth flow; if a coach edits a minor's record on Sprint 5, we must be able to reconstruct who did what. Without an audit log, that incident — or a later regulator inquiry about it — is unreviewable.
- **Article 9 biometric data.** Pose keypoints are special-category data. GDPR Art. 30 requires Records of Processing Activities; audit logging is the operational substrate for that record.
- **Cross-tier flows.** The QR check-in flow (`docs/security/qr-checkin-token-spec.md`) and the cross-tenant attribution worker (`docs/security/multi-tenant-isolation.md` §5) emit security-critical events that _must_ be reviewable with cryptographic integrity. Bolting this on at Sprint 17 means Sprints 3–16 of those flows produce an unauditable past.
- **SOC 2 Type II window.** Type II requires a 6-month observation window of _operating_ controls. If audit doesn't exist for the first 16 sprints, SOC 2 Type II by Sprint 24 is mathematically impossible.
- **PDPL Art. 19 (Egypt).** Requires controllers to maintain processing records. Same shape as GDPR Art. 30. Same Sprint-1 implication.
- **Federation procurement.** Federations will ask for an audit-event sample as part of vendor due diligence. We need to be able to produce one _before_ Sprint 22 (public launch).

The cost of building audit at Sprint 1 is small: ~3 engineering days for the schema, writer, and basic verifier; ~2 days per sprint thereafter to instrument new event types. The cost of bolting it on at Sprint 17 is rebuilding 16 sprints of behavior to emit retroactively meaningful events — and the regulatory exposure for the gap.

---

## 2. Required Events List

The following ~30 events must be emitted from the indicated sprint:

### 2.1 Authentication and session

| Event                                  | First emitted | Notes                                                 |
| -------------------------------------- | ------------- | ----------------------------------------------------- |
| 1. `auth.login_succeeded`              | Sprint 1      | Includes method (password / passkey / OAuth)          |
| 2. `auth.login_failed`                 | Sprint 1      | Reason: bad_password, locked, mfa_required, etc.      |
| 3. `auth.mfa_challenged`               | Sprint 1      | Method: totp, push, webauthn                          |
| 4. `auth.mfa_failed`                   | Sprint 1      |                                                       |
| 5. `auth.mfa_changed`                  | Sprint 1      | Adding/removing MFA methods                           |
| 6. `auth.password_changed`             | Sprint 1      | Self-service or admin reset                           |
| 7. `auth.session_token_issued`         | Sprint 1      | Token type, scope, exp                                |
| 8. `auth.session_token_revoked`        | Sprint 1      | Cause: user_logout, admin_force, suspected_compromise |
| 9. `auth.refresh_token_reuse_detected` | Sprint 1      | Token-reuse → user-wide session lockout               |

### 2.2 Authorization and scope

| Event                                | First emitted | Notes                                                 |
| ------------------------------------ | ------------- | ----------------------------------------------------- |
| 10. `authz.tenant_scope_changed`     | Sprint 4      | User switches into a different tenant scope           |
| 11. `authz.role_changed`             | Sprint 4      | E.g. coach added to club; athlete added to federation |
| 12. `authz.access_denied`            | Sprint 4      | Includes resource, attempted action, reason           |
| 13. `authz.annotation_scope_changed` | Sprint 8      | Per `docs/security/multi-tenant-isolation.md` §7      |

### 2.3 QR check-in

| Event                                   | First emitted | Notes                                                         |
| --------------------------------------- | ------------- | ------------------------------------------------------------- |
| 14. `checkin.token_issued`              | Sprint 16     | Per QR spec §11                                               |
| 15. `checkin.token_redeemed`            | Sprint 16     |                                                               |
| 16. `checkin.token_revoked`             | Sprint 16     | Cause: athlete_initiated, club_initiated, system              |
| 17. `checkin.second_redemption_attempt` | Sprint 16     | Alert-grade                                                   |
| 18. `checkin.club_allowlist_mismatch`   | Sprint 16     | Alert-grade                                                   |
| 19. `checkin.capability_misused`        | Sprint 16     | Capability presented at non-attribution endpoint; alert-grade |

### 2.4 Cross-tenant access

| Event                                      | First emitted | Notes                                                           |
| ------------------------------------------ | ------------- | --------------------------------------------------------------- |
| 20. `tenant_isolation.cross_tenant_access` | Sprint 4      | Privileged role read across tenants (DSAR, attribution, cohort) |
| 21. `tenant_isolation.disagreement`        | Sprint 4      | App-layer and RLS disagreed; alert-grade page on-call           |
| 22. `attribution.derived`                  | Sprint 16     | Per multi-tenant spec §5.4                                      |

### 2.5 Consent and erasure

| Event                           | First emitted | Notes                                                           |
| ------------------------------- | ------------- | --------------------------------------------------------------- |
| 23. `consent.granted`           | Sprint 1      | Purpose, version, granular categories                           |
| 24. `consent.revoked`           | Sprint 1      | Purpose, propagation status                                     |
| 25. `consent.parental_verified` | Sprint 3      | Method, verifier identity                                       |
| 26. `data.export_requested`     | Sprint 8      | DSAR initiation                                                 |
| 27. `data.export_delivered`     | Sprint 8      | Includes integrity hash                                         |
| 28. `data.erasure_requested`    | Sprint 8      | DSAR / Art. 17                                                  |
| 29. `data.erasure_completed`    | Sprint 8      | Per-store completion (DB, S3, training datasets, model weights) |

### 2.6 Admin and break-glass

| Event                      | First emitted | Notes                                               |
| -------------------------- | ------------- | --------------------------------------------------- |
| 30. `admin.action`         | Sprint 1      | Generic admin action with action-specific extra     |
| 31. `admin.viewer_access`  | Sprint 1      | Admin viewed PII data; the viewer itself is audited |
| 32. `breakglass.requested` | Sprint 6      |                                                     |
| 33. `breakglass.approved`  | Sprint 6      |                                                     |
| 34. `breakglass.action`    | Sprint 6      | Each action under break-glass role                  |
| 35. `breakglass.expired`   | Sprint 6      |                                                     |

### 2.7 ML and LLM

| Event                      | First emitted | Notes                                                 |
| -------------------------- | ------------- | ----------------------------------------------------- |
| 36. `model.promoted`       | Sprint 7      | New model version pushed to production; includes hash |
| 37. `model.rolled_back`    | Sprint 7      |                                                       |
| 38. `llm.prompt_response`  | Sprint 9      | Redacted prompt + response; per §6                    |
| 39. `llm.output_violation` | Sprint 9      | Validator flagged tool-call attempt or PII leak       |

### 2.8 Federation cohort

| Event                                    | First emitted | Notes                              |
| ---------------------------------------- | ------------- | ---------------------------------- |
| 40. `federation.cohort_metric_requested` | Sprint 18     | Federation operator queries cohort |
| 41. `federation.cohort_metric_denied`    | Sprint 18     | Insufficient consent / opt-in      |
| 42. `federation.config_pushed`           | Sprint 18     | Cloud → federation config update   |
| 43. `federation.config_applied`          | Sprint 18     | Federation accepted update         |
| 44. `federation.config_rejected`         | Sprint 18     | Federation refused update          |

This list is the **floor**. New event types are added by amendment to this spec; they require a CI-verified test that the event fires.

---

## 3. Event Schema

All events conform to one JSON shape:

```json
{
  "event_id": "01HX2ZP6X7Y8Z9A0B1C2D3E4F5",
  "event_type": "checkin.token_redeemed",
  "actor_principal": "club:c_01HV9R3E0M",
  "actor_role": "club_session_writer",
  "tenant_id": "org:c_01HV9R3E0M",
  "target_resource": "checkin_token",
  "target_id": "01HX2ZP6X7Y8Z9A0B1C2D3E4F5",
  "action": "redeem",
  "result": "success",
  "request_id": "req_01HX2ZP6...",
  "ip_addr_hash": "blake2b:9f3c...",
  "user_agent_hash": "blake2b:1abc...",
  "extra": {
    "session_id": "s_01HX300V",
    "redeeming_club_id": "c_01HV9R3E0M",
    "athlete_id_hash": "blake2b:7e21..."
  },
  "timestamp_ns": 1762371090123456789,
  "prev_event_hash": "blake2b:abc...",
  "event_hash": "blake2b:def..."
}
```

Field semantics:

- `event_id` — ULID-26, monotonic per writer.
- `event_type` — dotted namespace; matches §2 list.
- `actor_principal` — the entity that performed the action; may be `system:<service>` for non-user actors.
- `actor_role` — the role under which the action was performed; relevant for break-glass and privileged roles.
- `tenant_id` — the tenant the event is _about_. The same event may be replicated into multiple tenants if it concerns more than one (e.g. cross-tenant attribution writes a record in both Club and Solo audit chains).
- `target_resource` — typed string identifying the resource class (e.g. `checkin_token`, `session`, `annotation`).
- `target_id` — the specific resource ID.
- `action` — the verb (`create`, `read`, `update`, `delete`, `redeem`, `revoke`, `grant`, `derive`, etc.).
- `result` — `success` | `failure` | `denied`.
- `request_id` — propagated from the originating HTTP request for correlation.
- `ip_addr_hash` — BLAKE2b(IP || daily_salt). Daily salt rotates; raw IP not stored.
- `user_agent_hash` — BLAKE2b(UA). Useful for clustering bots without storing UA.
- `extra` — typed per-event-type bag; schema validated per event type.
- `timestamp_ns` — UTC nanoseconds since epoch from a monotonic source on the writer.
- `prev_event_hash` — hash of the immediately previous event in the _same tenant's chain_.
- `event_hash` — `BLAKE2b(canonical_serialization_of_all_other_fields)`. The chaining hash.

The chain is keyed by `tenant_id`. Each tenant has an independent linear chain. A genesis event per tenant initializes the chain.

### 3.1 Canonical serialization

For hashing, fields are serialized as canonical JSON: keys sorted, no whitespace, UTF-8, integers without trailing `.0`, booleans lowercase, nulls explicit. The library `pyserde` (or equivalent) produces this. Test fixtures verify deterministic output across machines.

### 3.2 Event-type-specific schemas

Each `event_type` has a JSON schema for `extra`. The writer validates `extra` against the schema before persisting. Unknown fields are rejected; missing required fields are rejected. Schemas live in `services/audit/schemas/<event_type>.json` and are versioned (`extra.schema_version` field). Schema migrations are append-only; old events retain their original schema version.

---

## 4. Storage

### 4.1 Append-only Postgres

Primary store is Postgres. Schema:

```sql
create table audit_events (
    event_id           text primary key,
    event_type         text not null,
    actor_principal    text not null,
    actor_role         text,
    tenant_id          text not null,
    target_resource    text,
    target_id          text,
    action             text not null,
    result             text not null,
    request_id         text,
    ip_addr_hash       text,
    user_agent_hash    text,
    extra              jsonb not null default '{}'::jsonb,
    timestamp_ns       bigint not null,
    prev_event_hash    text not null,
    event_hash         text not null
);

create index audit_events_tenant_time_idx
    on audit_events (tenant_id, timestamp_ns);
create index audit_events_actor_idx
    on audit_events (actor_principal, timestamp_ns);
create index audit_events_type_idx
    on audit_events (event_type, timestamp_ns);

revoke update, delete on audit_events from public, app_role;
grant insert on audit_events to audit_writer_role;
grant select on audit_events to audit_reader_role;
```

The application's normal `app_role` does _not_ have any privileges on `audit_events`. Writes go via a small audit-writer service that:

- Authenticates with its own credentials.
- Computes `prev_event_hash` and `event_hash`.
- INSERTs.
- Acks the caller.

The audit-writer is a hard architectural boundary. If the app process is compromised, the attacker still cannot UPDATE or DELETE audit rows (no privilege) and cannot easily forge the chain (would need the per-tenant most-recent-hash, which the audit-writer maintains in a separate cache).

### 4.2 Hash-chain per tenant

Per-tenant chain head is cached by the audit-writer. Insert is:

1. Acquire `pg_advisory_xact_lock(hash(tenant_id))`.
2. Read current chain head for tenant.
3. Compute new event's `prev_event_hash = head` and `event_hash`.
4. INSERT.
5. Update head cache.

Chain verification (background job, daily): walks each tenant's events in `timestamp_ns` order, recomputes hashes, asserts continuity. Discrepancy → high-severity alert.

### 4.3 Replication to write-once bucket

Nightly batch:

1. Export the prior day's audit events per tenant into newline-delimited JSON files.
2. Compute a manifest with file hashes, chain start/end hashes, and event counts.
3. Sign the manifest with an audit-archive signing key (separate from app signing keys).
4. Upload to S3 with **Object Lock** in **Compliance** mode for 7 years.
5. Verify upload by re-downloading and re-hashing.

In Compliance mode, even root cannot delete the object until retention expires. This is the canonical evidence in any future regulator inquiry.

### 4.4 Logically isolated DB

The audit DB is a separate Postgres database (separate connection string, separate role) from the operational DB. In production, prefer a separate Postgres instance entirely; in cost-constrained environments, separate database on the same instance with locked-down role grants is acceptable as a stop-gap. CI fails if the connection string for `app_role` resolves to the audit DB.

---

## 5. Retrieval and DSAR Support

### 5.1 Admin viewer

A web UI for security and DPO staff to query audit events. Capabilities:

- Filter by tenant, actor, event type, time range, result.
- Verify chain integrity for a tenant in a time range.
- Export results as signed CSV or JSONL with manifest.

The viewer is itself audited: every query emits `admin.viewer_access` with the search parameters. The DPO can review the DPO's own queries (auditors-audit-the-auditors).

### 5.2 Per-athlete DSAR export

When a user requests their data (GDPR Art. 15 / PDPL Art. 9):

1. The DSAR service assumes `dsar_exporter` role.
2. It collects audit events where the user is the actor or the target across all tenants where they appear.
3. It produces a signed, encrypted ZIP delivered via secure download with TTL.
4. `data.export_requested` and `data.export_delivered` events are themselves audit-logged.

### 5.3 Per-tenant export for federation compliance

A federation may need to produce its own RoPA evidence. The federation operator has read access to its tenant's audit chain via the on-prem viewer. Cloud has no role in this — the federation's audit chain is local to the federation's stack.

---

## 6. PII Redaction in Audit

The audit log itself must not become a PII leak vector.

### 6.1 Network identifiers

- `ip_addr` → BLAKE2b with daily-rotated salt. We can correlate within a day, not across days.
- `user_agent` → BLAKE2b. Useful for clustering, not for fingerprinting individuals long-term.

### 6.2 Direct identifiers in `target_id` and `extra`

- `athlete_id` is _never_ stored raw in the audit log for events that pertain to athletes. Use `athlete_id_hash` (BLAKE2b with a per-tenant key from KMS), and a separate `athlete_id_pseudonym_map` table accessible only to the DSAR exporter and DPO viewer.
- For non-athlete actors (coaches, admins), the principal ID is stored directly because they are not the protected class.

### 6.3 Free-text fields

Any free-text in `extra` (e.g. an admin's reason for a break-glass request) goes through:

1. **PII NER pass.** Named-entity recognition strips obvious PII (names, emails, phone numbers, addresses).
2. **Length cap.** 2KB per `extra` field; longer values are truncated with a marker.
3. **Pattern denylist.** Credit-card-number-shaped strings, JWT-shaped strings, bearer tokens are explicitly redacted.

### 6.4 LLM prompt and response

The `llm.prompt_response` event is the most PII-sensitive. Pipeline:

1. Athlete identifiers in the prompt are already replaced with stable pseudonyms before the LLM ever sees them (per Threat Model §4.4).
2. Before the prompt is written to the audit log, an additional NER + denylist pass runs to catch anything that slipped through.
3. The response goes through the same pipeline.
4. The audit event records the _redacted_ prompt + response, plus an `original_hash` so we can verify in the future that a redaction was applied to a specific original (without storing the original).
5. Prompts and responses are stored only when sampling / debugging requires it, with a 90-day default retention shorter than other audit events. This is configurable per tenant.

### 6.5 Re-identifiability review

Quarterly, the DPO samples 100 audit events at random and assesses whether the redacted form still permits re-identification of an individual. If yes, the redaction policy is tightened.

---

## 7. Alerting

The following events are alert-grade and page on-call SRE:

- `auth.login_failed` spike (>X failures from a single IP-hash window) → credential-stuffing
- `auth.refresh_token_reuse_detected` → potential session hijack
- `tenant_isolation.disagreement` → potential breach
- `checkin.second_redemption_attempt` → potential capability replay
- `checkin.club_allowlist_mismatch` → potential club spoofing
- `checkin.capability_misused` → potential XSS exfil
- `breakglass.action` outside an approved scope → potential abuse
- Chain verification failure in any tenant
- `llm.output_violation` rate spike → prompt injection campaign

Lower-severity anomalies (unusual data export volume, model rollback, federation config rejection) ticket but do not page.

---

## 8. CI Invariants

The following are blocking checks on every backend PR:

1. **Event coverage.** A static analyzer maps every API endpoint to the events it must emit (per a yaml manifest). A test runs each endpoint against fixtures and verifies the right events appear in the audit chain. Coverage gaps fail the build.
2. **Schema validation.** Every emitted `extra` validates against its event-type schema; CI enforces.
3. **No raw PII in audit fixtures.** A linter scans test audit events for raw IPs, emails, phone numbers, athlete IDs in unhashed form. Hits fail the build.
4. **Hash chain test.** A unit test inserts 1k events under a tenant, verifies chain continuity, then mutates one row in a separate test DB and verifies the verifier flags the break.
5. **Privilege test.** A test verifies that `app_role` cannot UPDATE or DELETE `audit_events` (catches accidental grant additions in migrations).
6. **Replication test.** A test verifies that the nightly export job produces a signed manifest whose signature verifies against the archive key.
7. **Redaction test.** A test feeds known-PII strings into `llm.prompt_response` and verifies they are redacted before persistence.

These tests run in CI and locally via `make audit-tests`.

---

## 9. Operational Runbook (Summary)

- **New event type added:** add to §2 list, add JSON schema, add coverage test, deploy audit-writer with new schema version, then deploy emitting code. Order matters: writer first.
- **Chain hash mismatch alert:** stop new writes for the affected tenant; preserve forensic snapshot; investigate before resuming.
- **Audit DB outage:** application **fails closed** for write-side actions that require audit (consent grant, scope change, break-glass). Read-only paths continue. We do not degrade-to-no-audit.
- **Regulator inquiry:** DPO uses admin viewer to produce signed export; cross-references with write-once bucket archive for chain integrity proof.

---

## 10. Sprint-by-Sprint Onboarding Plan

Aligning with the resequencing in `docs/reviews/07-compliance-auditor.md`:

| Sprint | Audit deliverable                                                                                |
| ------ | ------------------------------------------------------------------------------------------------ |
| 1      | Audit DB + writer service + events 1–9, 23–24, 30–31. Hash chain operational.                    |
| 2      | Threat model ratified; audit event coverage manifest in CI.                                      |
| 3      | Events 25 (parental consent verification) added.                                                 |
| 4      | Events 10–12, 20–21 (tenant isolation) added; disagreement alert wired.                          |
| 6      | Events 32–35 (break-glass) added; SOC 2 controls implementation begins.                          |
| 7      | Events 36–37 (model promotion) added.                                                            |
| 8      | Events 13, 26–29 (annotation scopes, DSAR) added; pull-from-original-Sprint-17.                  |
| 9      | Events 38–39 (LLM) added with redaction pipeline.                                                |
| 16     | Events 14–19, 22 (QR check-in, attribution) added.                                               |
| 18     | Events 40–44 (federation) added; SOC 2 Type I audit.                                             |
| 24     | SOC 2 Type II observation window closes; audit chain end-to-end demo for federation procurement. |

---

End of audit logging spec v1.0.
