"""Add tenant_encryption_keys + erasure_tickets.

Revision ID: 0014_erasure
Revises: 0013_coaching_notes
Create Date: 2026-05-22

Right-to-erasure foundation (docs/compliance/right-to-erasure-
architecture.md): per-tenant DEK store for crypto-shredding (§2) and
the append-only erasure ledger (§5.2).
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0014_erasure"
down_revision = "0013_coaching_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_encryption_keys",
        sa.Column("tenant_id", sa.String(128), primary_key=True),
        sa.Column("key_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("wrapped_dek", sa.LargeBinary, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shredded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "erasure_tickets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column("athlete_user_id", sa.String(64), nullable=False),
        sa.Column("requested_by", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("references_json", sa.JSON, nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("erasure_tickets")
    op.drop_table("tenant_encryption_keys")
