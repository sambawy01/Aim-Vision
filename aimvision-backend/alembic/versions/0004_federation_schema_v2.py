"""federation schema v2 — coach profiles, joint-controller consent, camera clock
offset, shot events, federation_admin role.

Revision ID: 0004_federation_v2
Revises: 0003_rls_policies
Create Date: 2026-05-13

Per V2 Sprint Plan §EPIC 4.3 (federation-first schema migration) and §EPIC 4.1
(camera_clock_offset_ms baked in now, not Sprint 17).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_federation_v2"
down_revision = "0003_rls_policies"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # 1. Extend membership_role enum with `federation_admin`. Postgres-only:
    #    ALTER TYPE ADD VALUE; SQLite enums are CHECK constraints and a no-op
    #    here since the test schema is rebuilt from models via create_all.
    if _is_postgres():
        op.execute("ALTER TYPE membership_role ADD VALUE IF NOT EXISTS 'federation_admin'")

    # 2. coach_profiles — mirrors athlete_profiles, scoped per tenancy.
    op.create_table(
        "coach_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(64),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("certifications", sa.JSON, nullable=True),
        sa.Column("specializations", sa.JSON, nullable=True),
        sa.Column(
            "accepting_clients", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_coach_profile_user_tenant"),
    )
    op.create_index(
        "ix_coach_profiles_tenant_id", "coach_profiles", ["tenant_id"]
    )

    # 3. consent_records: joint-controller payload + processing-basis discriminator +
    #    forward link to a withdrawal request (Sprint 17).
    op.add_column(
        "consent_records",
        sa.Column(
            "processing_basis",
            sa.String(32),
            nullable=False,
            server_default="consent",
        ),
    )
    op.add_column(
        "consent_records",
        sa.Column("joint_controller_org_ids", sa.JSON, nullable=True),
    )
    op.add_column(
        "consent_records",
        sa.Column("joint_controller_agreement_ref", sa.String(1024), nullable=True),
    )
    op.add_column(
        "consent_records",
        sa.Column("withdrawal_request_id", sa.String(64), nullable=True),
    )

    # 4. recordings.camera_clock_offset_ms — Sprint 4 EPIC 4.1 explicit.
    op.add_column(
        "recordings",
        sa.Column("camera_clock_offset_ms", sa.BigInteger, nullable=True),
    )

    # 5. shot_events — append-only event stream per ADR-0006.
    op.create_table(
        "shot_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "shot_id",
            sa.String(64),
            sa.ForeignKey("shots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_kind", sa.String(64), nullable=False),
        sa.Column("monotonic_seq", sa.BigInteger, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("produced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_shot_events_tenant_id", "shot_events", ["tenant_id"])
    op.create_index("ix_shot_events_shot_id", "shot_events", ["shot_id"])
    op.create_index(
        "ix_shot_events_kind_seq", "shot_events", ["event_kind", "monotonic_seq"]
    )

    # 6. RLS for the two new tables. Mirrors the policy pattern from
    #    0003_rls_policies for the tenant-scoped tables.
    if _is_postgres():
        for table in ("coach_profiles", "shot_events"):
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
            op.execute(
                f"""
                CREATE POLICY {table}_tenant_isolation
                ON {table}
                USING (tenant_id = current_setting('aimvision.tenant_id', true))
                WITH CHECK (tenant_id = current_setting('aimvision.tenant_id', true))
                """
            )


def downgrade() -> None:
    if _is_postgres():
        for table in ("coach_profiles", "shot_events"):
            op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")

    op.drop_index("ix_shot_events_kind_seq", table_name="shot_events")
    op.drop_index("ix_shot_events_shot_id", table_name="shot_events")
    op.drop_index("ix_shot_events_tenant_id", table_name="shot_events")
    op.drop_table("shot_events")

    op.drop_column("recordings", "camera_clock_offset_ms")

    op.drop_column("consent_records", "withdrawal_request_id")
    op.drop_column("consent_records", "joint_controller_agreement_ref")
    op.drop_column("consent_records", "joint_controller_org_ids")
    op.drop_column("consent_records", "processing_basis")

    op.drop_index("ix_coach_profiles_tenant_id", table_name="coach_profiles")
    op.drop_table("coach_profiles")

    # Note: Postgres has no `ALTER TYPE ... DROP VALUE`. Reverting the
    # federation_admin role requires creating a replacement type and casting
    # every column over — too risky for an auto-downgrade. Leave the value in
    # place; rows referencing it would block a true rollback anyway.
