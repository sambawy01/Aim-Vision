"""Add coaching_notes table.

Revision ID: 0013_coaching_notes
Revises: 0012_drills
Create Date: 2026-05-22

Persists the structured LLM coaching note (docs/llm-coaching-notes-
schema.md) produced by the post-session pipeline. Multiple notes per
session are permitted (regeneration); consumers read the most recent.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0013_coaching_notes"
down_revision = "0012_drills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coaching_notes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, index=True),
        sa.Column(
            "session_id",
            sa.String(64),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("headline", sa.Text, nullable=False),
        sa.Column("tone_mode", sa.String(16), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("verifier_passed", sa.Boolean, nullable=False),
        sa.Column("degraded", sa.Boolean, nullable=False),
        sa.Column("confidence_overall", sa.Float, nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("taxonomy_version", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note_json", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_coaching_notes_session_created",
        "coaching_notes",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_coaching_notes_session_created", table_name="coaching_notes")
    op.drop_table("coaching_notes")
