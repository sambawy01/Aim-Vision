# AIMVISION Multi-Tenant Isolation Specification

**Owner:** Security Engineer + Backend Lead
**Status:** Draft v1.0 — must be ratified by Sprint 4 (before any tenant-scoped data lands in production)
**Source review:** `docs/reviews/06-security-engineer.md` §"Multi-Tenant Isolation Recommendation"
**Related:** `docs/security/threat-model.md` §4.2/4.3, `docs/security/qr-checkin-token-spec.md`, `docs/security/audit-logging-spec.md`

---

## 1. Tenancy Model

AIMVISION has **three concurrent tenant types**:

| Tenant type     | `tenant_id` form         | Owner                       | Examples                                                            |
| --------------- | ------------------------ | --------------------------- | ------------------------------------------------------------------- |
| Solo user       | `solo:{user_id}`         | The user themselves         | `solo:u_01HX2ZP4N0V8C7W3J6K9MQ5RTY`                                 |
| Club organization | `org:{org_id}`         | The club's admin team       | `org:c_01HV9R3E0M`                                                  |
| Federation      | `fed:{fed_id}`           | The federation's IT + DPO   | `fed:f_01HEGY1234` (e.g. Egypt national federation)                 |

A natural person can be **simultaneously**:

- a Solo subscriber (`solo:u_01...`),
- a member of one or more Clubs (`org:c_01...`, `org:c_02...`),
- a tracked athlete in a Federation (`fed:f_01...`).

Their data is **partitioned per tenancy**. Solo videos belong to the Solo tenant. Sessions captured by a club belong to the Club tenant. Federation cohort statistics belong to the Federation tenant. Cross-tier *derived* data flows (e.g. attribution copies) happen only through the explicit, audited mechanisms in §5.

The same row never exists in two tenants. If the same data is logically meaningful in two tenancies, it is *re-derived* in each, with provenance recorded.

### 1.1 Principal model

A request principal is the *(user, tenant, role)* triple active for that request. The principal is derived from:

- **The session token** (PASETO v4.public; `sub` = user_id).
- **The tenant scope chosen at request time** — frontends pass `X-Tenant-Scope: solo:u_01...` (default = the user's primary Solo tenancy). Coaches pick `org:c_01...` to enter their club workspace. Federation operators pick `fed:f_01...`.
- **The role** — derived server-side from the user's membership in that tenant (athlete, coach, club_admin, fed_admin, etc.). Never client-asserted.

The backend validates that the user is permitted in the requested tenant scope and role. If not, 403.

---

## 2. Cloud Floor: Postgres Row-Level Security

RLS is the **floor**, not the ceiling.

### 2.1 Schema invariant

Every tenant-scoped table:

```sql
create table sessions (
    id          text primary key,
    tenant_id   text not null,
    -- ... domain columns ...
    created_at  timestamptz not null default now()
);

alter table sessions enable row level security;
alter table sessions force row level security;

create policy sessions_tenant_isolation on sessions
  using (tenant_id = current_setting('app.current_principal', true));
```

Notes:

- `force row level security` ensures the policy applies even to the table owner. The application role we use is *not* the table owner anyway, but `force` removes a footgun.
- `current_setting('app.current_principal', true)` — `true` makes it return NULL if unset, so unset principal = empty result, not error. We *want* unset principal to fail closed at the app layer (§3); RLS just makes the DB return zero rows as defense-in-depth.
- The policy is `using` only (read-side). For writes, separate `with check` is added: `with check (tenant_id = current_setting('app.current_principal', true))`. A row inserted under tenant A cannot then be flipped to tenant B.

### 2.2 Per-request principal binding

Every request handler runs through middleware that:

1. Resolves the principal `(user, tenant, role)`.
2. On the connection acquired from the pool, runs:

   ```sql
   select set_config('app.current_principal', $1, true);
   ```

   The `true` makes this transaction-scoped — it is reset when the transaction ends (or when the connection is released to the pool, given we wrap each request in a transaction). This eliminates the leak class where a previous request's principal lingers.
3. Begins the transaction. All work happens inside.
4. On commit/rollback, `set_config(... true)` clears.

### 2.3 Cross-tenant queries — the explicit escape hatch

The platform must occasionally read across tenants:

- The attribution worker (§5) needs to read a Club session row and write a Solo tenant row.
- DSAR export needs to read everything for one user across all tenants where they appear.
- Federation cohort metrics aggregate Club sessions that opted in.

Each escape hatch uses a **named privileged role** (`attribution_writer`, `dsar_exporter`, `cohort_aggregator`). These roles are exempted from the RLS policy via `bypassrls = false` but a separate, narrow policy — they can SELECT/INSERT only the columns and rows they specifically need, and they can only run from designated worker contexts. The CI test harness verifies that no general-purpose API role can assume one of these privileged roles.

---

## 3. Application-Layer Scope Filter (Defense-in-Depth)

RLS must not be the only line of defense. SQL string concatenation, raw SQL bypass, ORM bugs, and DBA mistakes can all defeat RLS in narrow ways. We add an app-layer scope filter:

### 3.1 Repository wrapper

```python
class TenantScopedRepository:
    def __init__(self, principal: Principal, table: str, model: type):
        self.principal = principal
        self.table = table
        self.model = model

    def _require_principal(self):
        if self.principal is None:
            raise NoPrincipalError(self.table)
        if self.principal.tenant_id is None:
            raise NoTenantError(self.principal)

    def fetch(self, **filters) -> list:
        self._require_principal()
        # ORM query that ALWAYS adds tenant_id filter:
        return (Session.query(self.model)
                .filter_by(tenant_id=self.principal.tenant_id, **filters)
                .all())

    def create(self, **fields):
        self._require_principal()
        if "tenant_id" in fields and fields["tenant_id"] != self.principal.tenant_id:
            raise CrossTenantWriteError(self.principal, fields["tenant_id"])
        fields["tenant_id"] = self.principal.tenant_id
        # ...
```

All data access goes through `TenantScopedRepository`. Raw SQL is forbidden in business logic. The CI lints (Semgrep rules) reject:

- `text(` with f-strings or `%` formatting.
- Direct `Session.execute(...)` without a `tenant_id` filter.
- Any model query bypassing the repository.

### 3.2 Disagreement test

A CI test harness loads a test row in tenant A, then issues a query under tenant B's principal that *should* fail at both layers. The test asserts that:

1. The app-layer wrapper raises `NoPrincipalError` or filters out the row.
2. As a separate test, with the app-layer filter forcibly bypassed (white-box), RLS still returns zero rows.

If either layer disagrees with the other, CI fails. Both layers must report "tenant B cannot see tenant A's row."

### 3.3 Audit on disagreement

In production, if a query *would have been* filtered by the app layer but the database somehow returned a row from another tenant (signaled by a `tenant_id` mismatch in the result row), the application:

1. Drops the result.
2. Emits a high-severity audit event `tenant_isolation.disagreement` with sufficient context for forensics.
3. Pages on-call.

Disagreement should be impossible. If it ever fires, it is treated as a possible breach.

---

## 4. Federation On-Prem Isolation

Federations operate their own stack. The cloud control plane provides updates and observability, but cannot read federation tenant data without break-glass.

### 4.1 Per-federation isolation

Each federation gets:

- **Its own Postgres database.** Not a separate schema in a shared DB; a separate database (or separate server) entirely. `tenant_id` columns are still present so the same RLS policies apply within the federation, but the database is *not* shared with cloud or other federations.
- **Its own KMS root key.** BYOK option: the federation may bring an HSM and the cloud control plane provisions keys backed by it.
- **Its own Ollama instance.** Prompts and responses never leave the federation's network boundary. Cloud Ollama serves Solo and Club only.
- **Its own object storage bucket.** S3 in their region or MinIO on-prem. Signing keys for object URLs are local to the federation.
- **Its own audit log SIEM endpoint.** The federation's audit log is shipped to the federation's SIEM, not back to cloud. Cloud has no read access by default.

### 4.2 Control plane

- Cloud → federation API calls happen over mTLS with rotation; federation can require approval before applying any cloud-pushed update (model weights, schema migrations, config).
- Federation → cloud telemetry is opt-in per metric. Default opt-out for everything but heartbeat.

### 4.3 Break-glass admin

Cloud SRE may need to assist with an incident in federation tenant. The flow:

1. Cloud SRE creates a break-glass request: target federation, scope (e.g. "read sessions table for one athlete"), justification, ticket reference.
2. Federation DPO and cloud DPO both approve (two-person rule, can be reduced to one for federations that explicitly delegate).
3. Approval mints a *time-bounded, scope-bounded* role assumption. The role can only access what was approved.
4. Every action under the break-glass role is audit-logged into the *federation's* SIEM. Cloud also logs that break-glass was used, but does not see the per-action details by default — federation can choose to forward.
5. On expiry, the role assumption is revoked.

### 4.4 No shared signing keys

The cloud signing key and the federation signing keys are independent. A cloud key compromise does not let an attacker forge tokens valid against a federation. A federation key compromise is contained to that federation.

---

## 5. Cross-Tier Derived Report Pipeline

This is the **highest-risk surface** in the platform. The Solo athlete checks in at a Club session; the club captures the session video; the platform attributes specific frames to that athlete and produces a personalized Solo report. The pipeline below is the only sanctioned path. All other cross-tenant data flows are forbidden.

### 5.1 Step 1 — Club session capture

The club's session-writer:

1. Authenticates as a club coach or club ingest service.
2. Writes the full session record into the **Club tenant only** (`tenant_id = org:{club_id}`).
3. As frames are processed, attribution markers are written for each frame range whose pose/identity matches an attributed athlete. The `attributed_athlete_id` in the marker is *only* populated if a valid attribution capability (per `docs/security/qr-checkin-token-spec.md` §8) was presented for that athlete and that session.
4. Frames without a matched athlete are written with `attributed_athlete_id = NULL`.

The club tenant now holds the full session, with per-frame attribution metadata.

### 5.2 Step 2 — Sandboxed attribution worker

A Temporal-managed worker (we'll call it the `attribution_derive` worker) runs in a sandboxed context:

- It assumes the `attribution_writer` role, which has narrowly scoped privileges.
- It can SELECT from the Club tenant's `session_attributions` table for the specific `(session_id, attributed_athlete_id)` it has been dispatched for.
- It can SELECT derived shot features and pose tensors filtered to those frame ranges.
- It can INSERT into the Solo tenant (`solo:u_<athlete_id>`) for `derived_shots`, `derived_features`, `report_inputs`.
- It **cannot** SELECT raw video bytes.
- It **cannot** SELECT data outside the dispatched `(session_id, athlete_id)`.
- It **cannot** access any other Club's data, any other athlete's data, or anything in another federation.

The role's grants are explicit: SELECTs are scoped to specific columns; INSERTs are scoped to specific tables; UPDATE/DELETE are forbidden.

### 5.3 Step 3 — Signed time-range URL into Club video

The Solo report does **not** contain a copy of the Club's full video. Instead, the report references a **signed time-range URL** that the storage layer enforces:

```
GET https://video.aimvision.app/clips/c_01HV9R3E0M/s_01HX300V/clip.mp4
   ?start_ms=12345
   &end_ms=18901
   &athlete_id=ap_01HX2ZP4N0      # session-pseudonym
   &exp=1762378290
   &sig=<HMAC-SHA256 over query>
```

Storage-layer enforcement:

- The signing key is held by storage; the API has signing privilege but storage validates.
- The URL is short-lived (15 minutes default; tunable per tier).
- The URL is bound to the requesting athlete's pseudonym; storage validates the `athlete_id` claim against the session's attribution markers — if the requested time range is not attributed to that pseudonym, 403.
- The URL is single-byte-range — it cannot fetch frames outside `[start_ms, end_ms]`.

The Solo athlete's mobile app fetches the clip via the signed URL. The Club's full video is never copied into the Solo tenant.

### 5.4 Step 4 — Audit record

Every derive run emits an audit record:

```json
{
  "event_type": "attribution.derived",
  "session_id": "s_01HX300V",
  "athlete_id_hash": "...",
  "frames_attributed": 1248,
  "frames_excluded": 312,
  "attribution_confidence_p50": 0.91,
  "attribution_confidence_p10": 0.78,
  "worker_role": "attribution_writer",
  "request_id": "..."
}
```

This is in the audit log per `docs/security/audit-logging-spec.md`.

### 5.5 Step 5 — Confidence-gated report

If the lower-percentile confidence (e.g. p10) is below threshold (say 0.70), the report is **blocked** and a coach-review task is surfaced. The coach must manually confirm or correct attributions before the report is released to the athlete. This guards against cases where the pose-based attribution is unreliable (e.g. crowded firing line).

### 5.6 Pipeline invariants

| Invariant                                                                                              | How enforced                                                                                  |
| ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| Only attributed frames flow to Solo tenant.                                                            | Worker SELECT predicate; CI test verifies non-attributed frames are not visible to worker.    |
| Raw video bytes never copied to Solo tenant.                                                           | Worker role grants exclude raw-video columns; storage signed URLs replace raw access.         |
| Worker cannot exfiltrate other clubs' data.                                                            | Role grants scoped to dispatched `(club_id, session_id)`.                                     |
| Confidence-gated reports prevent silent misattribution.                                                | p10 threshold check; manual coach review required below threshold.                            |
| Every derive emits an audit record visible in both Club and Solo tenant audit logs.                    | Audit log writer fans out per-tenant.                                                          |

---

## 6. Attack Mitigations

| Attack                                                                                          | Defense                                                                                                                                          |
| ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| IDOR via `tenant_id` swap in path parameter or body                                              | App-layer wrapper rejects mismatched tenant; RLS catches anything that slips past the wrapper.                                                    |
| SQL injection that bypasses app-layer filter                                                    | RLS still applies at the DB. Plus: ORM-only, parameter binding, Semgrep CI rules forbidding string-concatenated SQL.                              |
| Worker forging cross-tenant write by inserting `tenant_id = solo:other_user`                     | Role permissions only allow INSERT into the dispatched athlete's tenant; `with check` policy verifies; CI test harness exercises this.            |
| Compromised application role attempting to disable RLS                                           | The application role does not own the table; cannot `alter table ... disable row level security`. Only DBA role (separate, MFA-gated) can.        |
| Signed-URL replay against a different athlete                                                    | Signature includes athlete pseudonym; storage validates; URL TTL short.                                                                           |
| Signed-URL leak via caching proxy                                                                | `Cache-Control: private, no-store`; storage validates `Referer` is mobile-app/dashboard; pseudonym binding still enforces.                        |
| Coach in Club B attempting to read Club A's session because they happen to be in both           | Principal is per-request; coach acting in Club B has tenant scope `org:b`; cannot reach `org:a` rows.                                              |
| Federation operator attempting to read cloud Solo data                                           | Federation has no DB credentials for cloud Solo Postgres; control plane API does not expose Solo data to federation operators.                    |
| DSAR export role used to dump entire DB                                                          | Role is per-user-export-bound; rate-limited; every export audit-logged; bulk anomaly alerts.                                                     |
| Backup or read-replica leaking cross-tenant data                                                 | Backups are per-tenant DEK-encrypted (crypto-shredding); read replicas inherit RLS policies; CI verifies replica policy state.                   |

---

## 7. Coach Annotation Visibility Scopes

Coach annotations are first-class data with explicit visibility scopes:

| Scope                       | Who sees                                                                                  | Default |
| --------------------------- | ----------------------------------------------------------------------------------------- | ------- |
| `private`                   | The annotating coach only                                                                 | yes     |
| `share_with_athlete`        | + the athlete who is the subject                                                          |         |
| `share_with_club`           | + other coaches in the same club, scoped to athletes they are assigned to                 |         |
| `share_with_federation`     | + federation operators, only for athletes the federation tracks                           |         |

Rules:

- **Default scope = `private`.** Most restrictive default. Sharing requires affirmative action.
- **Re-share blocked.** A coach in Club A with `share_with_club` access cannot re-share to Club B. Re-share semantics are forbidden at the API layer; clients cannot opt in.
- **Deletion propagates.** Deleting an annotation removes it from all derived report bundles immediately and from cached views within 60 seconds. Soft-delete in DB with hard-delete after 30 days (which is well within GDPR Art. 17 SLA).
- **Scope changes are audit-logged.** `annotation.scope_changed` event with `from`, `to`, `actor_principal`, `target_id`. Athletes are notified when an annotation about them gets shared more widely.
- **Athlete revocation.** The athlete can revoke `share_with_athlete` and downstream scopes for any annotation about themselves. Coach view returns to `private`.

The repository for annotations is a specialization of `TenantScopedRepository` that adds scope evaluation in addition to tenant filtering.

---

## 8. Audit Log Integrity

The audit log is *itself* a tenant-scoped data store with extra protections:

- **Append-only.** Application role has only INSERT, never UPDATE/DELETE. Schema enforces via `revoke update, delete on audit_events from app_role`.
- **Hash-chained per tenant.** Each event includes `prev_event_hash` and `event_hash`. Verifying the chain confirms no event was excised.
- **Replicated to write-once bucket.** Nightly batch shipping to S3 with Object Lock + Compliance retention (7 years). Even if the operational DB is compromised, the historical chain is preserved.
- **Logically isolated DB.** Audit DB is on a separate Postgres role, separate connection string, separate (or hardened) host. The application role for normal API requests cannot connect to the audit DB; only the audit-writer role can. A compromised app role cannot tamper with the audit chain.

Full schema and ops detail in `docs/security/audit-logging-spec.md`.

---

## 9. Data Residency

Tenant data location is bound to the athlete's residency:

| Athlete's residency           | Storage region                                                          | Notes                                                                                                                       |
| ----------------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Egypt (athlete or federation) | AWS me-south-1 (Bahrain) **or** on-prem Egypt mirror                     | PDPL; cross-border transfer requires PDPC permit + per-athlete TIA documented in `docs/compliance/`.                          |
| EU                            | AWS eu-west-1 (Dublin) or eu-central-1 (Frankfurt)                       | GDPR Art. 44–49; SCCs in DPA; TIA per docs/compliance/.                                                                     |
| UK                            | AWS eu-west-2 (London)                                                  | UK GDPR; UK IDTA in DPA.                                                                                                     |
| US                            | AWS us-east-1 or us-west-2                                              | COPPA for under-13.                                                                                                          |
| Other                         | Closest GDPR-equivalent region; documented in onboarding                | Per-jurisdiction TIA.                                                                                                        |

Data flows across regions only with:

- A documented TIA for the recipient region.
- Per-athlete consent if the cross-region flow is for a non-routine purpose (e.g. coaching by a coach in another country).
- Audit logging of the cross-region access in both source and destination regions.

The mobile app and dashboard route to the closest in-region API edge based on the user's home region, which is fixed at signup.

---

## 10. Test Plan (30+ Cases)

### 10.1 Tenant isolation (RLS + app filter)

| #  | Case                                                                                                                  | Expected                                                                                  |
| -- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 1  | User in tenant A queries `/sessions` with header `X-Tenant-Scope: solo:userA`; sees only their data                    | 200, only A's rows                                                                       |
| 2  | User in tenant A spoofs `X-Tenant-Scope: solo:userB`                                                                  | 403 (not a member of userB's solo tenant)                                                 |
| 3  | Direct DB query as `app_role` without `app.current_principal` set                                                     | RLS returns 0 rows                                                                        |
| 4  | App-layer wrapper called without principal                                                                            | `NoPrincipalError` raised                                                                  |
| 5  | App layer bypassed (white-box test) but principal set on connection                                                   | RLS still filters correctly                                                                |
| 6  | INSERT with `tenant_id` value not equal to current principal                                                          | RLS `with check` rejects                                                                   |
| 7  | UPDATE attempting to flip `tenant_id` of an existing row                                                              | RLS `with check` rejects                                                                   |
| 8  | Two concurrent requests on same connection (pool reuse) — principal A then B                                          | B's request never sees A's principal (verified via `set_config(... true)` reset)           |
| 9  | DBA role alters policy; CI catches the drift on next migration check                                                  | CI fails                                                                                   |
| 10 | Privileged role `attribution_writer` reads cross-tenant only within its grant scope                                   | 200; out-of-scope reads → permission denied                                                |

### 10.2 Scope enforcement (annotations)

| #  | Case                                                                                                                  | Expected                                                                                  |
| -- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 11 | Coach C1 creates annotation with default scope; coach C2 in same club queries                                         | C2 does not see C1's annotation                                                            |
| 12 | C1 sets scope `share_with_club`; C2 in same club queries                                                              | C2 sees it                                                                                 |
| 13 | C2 attempts to re-share C1's annotation to another club                                                               | 403 `reshare_forbidden`                                                                   |
| 14 | Athlete revokes share for an annotation about them                                                                    | Subsequent C1 view shows only their private form; C2 view 404                              |
| 15 | C1 deletes an annotation                                                                                              | All cached views drop within 60s; report bundles re-derived without it                     |
| 16 | Scope change emits `annotation.scope_changed` audit event with from/to                                                 | Audit verified; athlete notified                                                            |

### 10.3 Cross-tier attribution (the high-risk surface)

| #  | Case                                                                                                                  | Expected                                                                                  |
| -- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 17 | Worker dispatched for `(session_s, athlete_a)` reads session_s's frames                                                | Reads only attributed frames                                                                |
| 18 | Worker attempts to read frames not attributed to athlete_a                                                            | Permission denied                                                                          |
| 19 | Worker attempts to INSERT into wrong Solo tenant                                                                       | Permission denied (role grant)                                                              |
| 20 | Worker attempts to SELECT raw video bytes                                                                              | Permission denied (column-level grant)                                                      |
| 21 | Solo athlete fetches signed URL for time range outside their attribution                                               | Storage 403                                                                                 |
| 22 | Signed URL reused by different athlete pseudonym                                                                       | Storage 403                                                                                 |
| 23 | Signed URL used after `exp`                                                                                           | Storage 403                                                                                 |
| 24 | Confidence p10 = 0.65 (below threshold); report blocked, coach-review task created                                    | Report not visible to athlete; coach gets review task                                        |
| 25 | Audit log emitted for derive includes both Club and Solo tenant entries                                                | Verified                                                                                   |

### 10.4 Federation on-prem boundary

| #  | Case                                                                                                                  | Expected                                                                                  |
| -- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 26 | Cloud admin attempts to read federation tenant data without break-glass                                               | 403; audit event in cloud + federation                                                     |
| 27 | Break-glass approved; admin reads narrow scope; action audit-logged in federation SIEM                                | 200 within scope; SIEM event present                                                       |
| 28 | Federation cohort metric requires opt-in; not opted in → metric not aggregated                                        | Metric returns "not available"                                                              |
| 29 | Federation Ollama instance never receives prompts from another federation                                             | Verified by test fixture asserting per-federation Ollama URL                                |
| 30 | Cloud signing key compromise drill — federation tokens unaffected                                                      | Federation token validators do not trust the cloud key                                     |

### 10.5 Misc

| #  | Case                                                                                                                  | Expected                                                                                  |
| -- | --------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| 31 | DSAR export role rate-limited to one export per athlete per day                                                       | Second request 429                                                                         |
| 32 | Backup encrypted with per-tenant DEK; deleting DEK renders backup unreadable                                          | Restore attempt fails; documented in IR runbook                                             |
| 33 | Read replica inherits RLS policies                                                                                    | Replica returns same per-principal results                                                  |
| 34 | Athlete in two clubs sees clean separation between Club A and Club B contexts                                         | No cross-bleed; verified via fixtures                                                       |
| 35 | Cross-region access (EU coach views Egypt athlete) without consent                                                     | Blocked + audit event                                                                       |

These tests must run in CI on every backend change. Disagreement between RLS and app-layer is treated as a blocker.

---

End of multi-tenant isolation spec v1.0.
