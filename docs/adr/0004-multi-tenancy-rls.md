# ADR-0004: Multi-Tenancy via Postgres Row-Level Security with Application-Layer Defense in Depth

**Status:** Accepted · **Date:** 2026-05-06 · **Owner:** Software Architect

## Context

AIMVISION serves three tenant types — Solo (single athlete), Club (a sporting-clays club with coaches and members), and Federation (a national governing body with multiple affiliated clubs and athletes) — across two deployment topologies (cloud-managed and federation on-prem). The original V1 sprint plan does not specify the multi-tenancy model. This is a foundational decision: every table, every query, every cache key, and every audit log entry depends on the tenant boundary.

The cost of getting this wrong is severe and asymmetric. A cross-tenant data leak — federation A's athletes appearing in federation B's coach dashboard, or one club's diagnostic patterns informing another club's cohort report without consent — is a disclosable security incident under GDPR and Egypt's PDPL ([Compliance auditor review](../reviews/07-compliance-auditor.md)) and a reputational kill shot in a market where federations procure on the basis of trust. The cost of getting it right is one well-designed schema and one disciplined query layer.

The candidates are:

1. **Schema-per-tenant.** A separate Postgres schema per tenant. Strong isolation, easy to drop a tenant, easy to reason about. **Migration hell at scale**: every Alembic migration runs against thousands of schemas, taking hours and breaking on the slowest one. Onboarding a new tenant means a schema creation and migration pass on every deploy. Rejected by the [Software Architect review §Missing Concerns](../reviews/03-software-architect.md).
2. **Database-per-tenant.** Each tenant gets a logical database (or even a separate cluster). Maximum isolation. Operationally heavy. Right answer for federation on-prem (where the federation's data must not commingle with anyone else's, ever) but overkill for tens of thousands of Solo subscribers.
3. **Row-level tenancy with `organization_id` everywhere + Postgres Row-Level Security (RLS).** One schema, one database, every table has an `organization_id` column, RLS policies enforce tenant scope at the database boundary. Cheap to operate, easy to migrate, and the security boundary is enforced by Postgres itself rather than by every developer remembering to add `WHERE organization_id = ?`. The [Software Architect review §Missing Concerns](../reviews/03-software-architect.md) recommends this for cloud Solo/Club.

The hybrid that fits the deployment topology:

- **Cloud Solo and Club:** RLS on a shared cluster. Tens of thousands of small tenants, one database to migrate, one cluster to operate.
- **Cloud Federation (managed but isolated):** dedicated logical database within the same CloudNativePG cluster. Federation can be migrated to a dedicated cluster on demand without code changes (the application connection string is per-federation; the data model is identical).
- **Federation on-prem:** a separate database (the entire stack is a separate Helm install). Sovereignty and data residency are satisfied by the deployment shape itself, not by row filters.

## Decision

**Postgres Row-Level Security as the floor for cloud Solo/Club, application-layer scope filter as defense-in-depth, separate database per federation on-prem.** Specifically:

### Schema rules

1. Every multi-tenant table has a non-null `organization_id UUID NOT NULL REFERENCES organizations(id)` column. There is no exception. Tables that do not have an `organization_id` (e.g., `model_versions`, `system_audit_log`) are explicitly globally scoped and called out in the schema comment.
2. Every multi-tenant table has an RLS policy keyed on `current_setting('app.current_org_id')::uuid`. Example:

   ```sql
   ALTER TABLE shots ENABLE ROW LEVEL SECURITY;
   CREATE POLICY shots_tenant_isolation ON shots
     USING (organization_id = current_setting('app.current_org_id')::uuid);
   ```

3. The application connects to Postgres as a non-superuser role for which RLS is **not** bypassable (`NOBYPASSRLS`). Migrations and admin tooling use a separate role.
4. Every request handler sets `app.current_org_id` from the validated bearer token at the start of the connection's request scope (via SQLAlchemy event listener) and clears it on connection return to the pool.
5. The application layer **also** scopes every query by `organization_id` in the WHERE clause. This is defense in depth: RLS is the floor that catches developer error before it becomes a leak, and the application filter is the first line that catches missing-config error before it becomes a query plan that scans every tenant's rows. Both layers must agree.

### Cross-tenant pipelines

Some workflows legitimately read data from multiple tenants (e.g., the federation talent-ID report aggregates anonymized clay-shooting data across affiliated clubs inside one federation). These flows are:

- Implemented exclusively in a small set of Temporal activities (ADR-0007) marked `@cross_tenant`.
- Use a service role with broader RLS policies that explicitly scope to a federation hierarchy (`organization_id IN (SELECT id FROM organizations WHERE federation_id = $1)`).
- Write to derived tables that are themselves single-tenant (the federation owns the derived report) and never to source tables.
- Logged in a dedicated `cross_tenant_access_audit` append-only table with the federation ID, the actor, the activity name, and the row count read.

The proof that this pipeline cannot leak data outside the federation hierarchy is in `docs/security/multi-tenant-isolation.md`. The [Software Architect review §Missing Concerns](../reviews/03-software-architect.md) called this out as the place where most RLS deployments quietly break.

### Federation on-prem

The on-prem appliance ships a full Helm chart (ADR-0005) with its own CloudNativePG cluster. There is no cloud control plane connection. RLS is still enabled — a federation may have multiple sub-organizations (e.g., regional academies) that need internal isolation — but the outermost boundary is the appliance itself.

### Connection pooling

We use **PgBouncer in transaction-pool mode** in front of CloudNativePG. Because `current_setting` is session-scoped, transaction pooling requires that we set the org ID as a `LOCAL` setting at the start of each transaction (`SET LOCAL app.current_org_id = ...`) — not at connection check-out. The SQLAlchemy event listener implements this. We test this with a chaos suite that intentionally interleaves transactions across orgs and asserts that no row from org A is ever returned to org B.

## Consequences

**Easier:**

- One schema, one migration story for cloud. Onboarding a new tenant is a single `INSERT INTO organizations` plus user provisioning — no DDL.
- Database-level enforcement of tenant boundary. Even a developer who forgets the `WHERE organization_id` clause in a future query gets zero rows back, not someone else's data.
- Federation on-prem deployment is a config change (different connection string), not a code change.
- The cross-tenant pipeline is the only privileged path; everything else is sandboxed by default.

**Harder:**

- Every developer must internalize that RLS is on and that bypassing requires intent (a flagged service role and a code-review-gated activity decorator).
- Connection-pool semantics with RLS require care. Transaction-pool mode plus `SET LOCAL` is the only safe combination; session pool mode would leak the setting across requests.
- Performance tuning requires care: RLS policies become part of the query plan, and a poorly-written policy can defeat index usage. We measure this in CI with `EXPLAIN ANALYZE` regression tests on the top 20 queries.
- Schema-per-tenant has one operational win — easy "drop tenant" — that we lose. We replace it with a Temporal `ErasureWorkflow` that scrubs every owned row across every owned data store (Postgres, S3, vector store, search index, MLflow training-data lineage). Detail in `docs/compliance/gdpr-erasure-flow.md`.

**Reversibility:** Medium. Migrating to schema-per-tenant later is painful but bounded. Migrating to database-per-tenant is the natural growth path for Federation tier and is already supported by the deployment topology.

## Alternatives Considered

1. **Schema-per-tenant.** Rejected — migration hell at scale.
2. **Database-per-tenant for everyone.** Rejected for cloud Solo/Club — operational cost is multiplied by the tenant count. Adopted for federation on-prem.
3. **No RLS, application-only scope filter.** Rejected. One missing `WHERE` clause is a cross-tenant leak. We trust the database boundary, not developer discipline.
4. **No application filter, RLS only.** Rejected. RLS without the application filter forces full-table-scan plans because the optimizer cannot push the policy predicate down through some query shapes; we want both layers to agree.
5. **Citus / sharded Postgres.** Rejected for V1 — premature scale concern. Revisit if Solo subscriber count exceeds a million.

## References

- [Software Architect review §Missing Concerns (multi-tenancy)](../reviews/03-software-architect.md)
- [Compliance auditor review](../reviews/07-compliance-auditor.md) — GDPR, Egypt PDPL data residency obligations.
- `docs/security/multi-tenant-isolation.md` — full proof of the cross-tenant report pipeline (predicted filename, owned by Security Engineer).
- `docs/compliance/gdpr-erasure-flow.md` — the right-to-erasure Temporal workflow.
- Postgres Row Security: <https://www.postgresql.org/docs/current/ddl-rowsecurity.html>
- "Designing Data-Intensive Applications" Ch. 5 (Kleppmann) — the trade-off table this ADR is built on.
