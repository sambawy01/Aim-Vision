"""Enable Row-Level Security on every tenant-scoped table (ADR-0004).

Idempotent: re-running on a database that already has the policies is a no-op.

Revision ID: 0003_rls_policies
Revises: 0002_audit_log
"""

from __future__ import annotations

from alembic import op

# Renamed from "0003_rls" — the rest of the chain references this migration
# as "0003_rls_policies" (see 0004_federation_schema_v2.py::down_revision),
# so any deployment running alembic against Postgres crashes with
# `KeyError: '0003_rls_policies'`. Latent until PR #96's compose-stack
# work tried to actually run `alembic upgrade head`. No production
# deployment has applied this migration under either id.
revision = "0003_rls_policies"
down_revision = "0002_audit_log"
branch_labels = None
depends_on = None

TENANT_TABLES = (
    "orgs",
    "memberships",
    "cohorts",
    "athlete_profiles",
    "consent_records",
    "sessions",
    "recordings",
    "shots",
    "annotations",
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        return  # RLS is a Postgres feature; SQLite (tests) is a no-op.

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")
        # Drop-and-recreate is the simplest idempotent recipe.
        op.execute(f"DROP POLICY IF EXISTS tenant_iso ON {table};")
        op.execute(
            f"""
            CREATE POLICY tenant_iso ON {table}
            FOR ALL
            USING (tenant_id = current_setting('app.current_principal', true))
            WITH CHECK (tenant_id = current_setting('app.current_principal', true));
            """
        )


def downgrade() -> None:
    if not _is_postgres():
        return
    for table in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_iso ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")
