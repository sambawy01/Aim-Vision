"""Global drill catalog table (DDL only; rows seeded at app startup).

Revision ID: 0012_drills
Revises: 0011_session_partial_flag
Create Date: 2026-05-22

The LLM coaching note's `recommended_drills` reference drill ids the
verifier checks against this catalog. Drills are a global reference
library (no tenant_id, no RLS). The canonical rows live in
`app.data.drills.DRILL_CATALOG` and are upserted idempotently on app
startup (`app.services.drills.ensure_drills_seeded`), so the catalog
is present whether the schema came from migrations (prod) or
`create_all` (tests). This migration only creates the table.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0012_drills"
down_revision = "0011_session_partial_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drills",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("discipline", sa.String(32), nullable=False, server_default="all"),
        sa.Column("target_categories", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("drills")
