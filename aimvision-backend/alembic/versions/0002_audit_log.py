"""audit_events table + role grants (per audit-logging-spec.md §4.1).

Revision ID: 0002_audit_log
Revises: 0001_federation
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0002_audit_log"
down_revision = "0001_federation"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    extra_type = sa.JSON().with_variant(JSONB, "postgresql")

    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("actor_principal", sa.String(255), nullable=False),
        sa.Column("actor_role", sa.String(64), nullable=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("target_resource", sa.String(128), nullable=True),
        sa.Column("target_id", sa.String(255), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=True),
        sa.Column("ip_addr_hash", sa.String(128), nullable=True),
        sa.Column("user_agent_hash", sa.String(128), nullable=True),
        sa.Column("extra", extra_type, nullable=False, server_default=sa.text("'{}'")),
        sa.Column("timestamp_ns", sa.BigInteger, nullable=False),
        sa.Column("prev_event_hash", sa.Text, nullable=False),
        sa.Column("event_hash", sa.Text, nullable=False),
    )
    op.create_index("audit_events_tenant_time_idx", "audit_events", ["tenant_id", "timestamp_ns"])
    op.create_index("audit_events_actor_idx", "audit_events", ["actor_principal", "timestamp_ns"])
    op.create_index("audit_events_type_idx", "audit_events", ["event_type", "timestamp_ns"])

    if _is_postgres():
        # Roles created idempotently. The CREATE ROLE syntax doesn't accept IF NOT EXISTS,
        # so we wrap in a DO block.
        op.execute(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'audit_writer_role') THEN
                CREATE ROLE audit_writer_role NOLOGIN;
              END IF;
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'audit_reader_role') THEN
                CREATE ROLE audit_reader_role NOLOGIN;
              END IF;
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_role') THEN
                CREATE ROLE app_role NOLOGIN NOBYPASSRLS;
              END IF;
            END
            $$;
            """
        )
        op.execute("REVOKE ALL ON audit_events FROM PUBLIC;")
        op.execute("REVOKE UPDATE, DELETE ON audit_events FROM app_role;")
        op.execute("GRANT INSERT ON audit_events TO audit_writer_role;")
        op.execute("GRANT SELECT ON audit_events TO audit_reader_role;")


def downgrade() -> None:
    op.drop_index("audit_events_type_idx", table_name="audit_events")
    op.drop_index("audit_events_actor_idx", table_name="audit_events")
    op.drop_index("audit_events_tenant_time_idx", table_name="audit_events")
    op.drop_table("audit_events")
