"""Add sessions.partial_session boolean for degraded-mode reporting.

Revision ID: 0011_session_partial_flag
Revises: 0010_shot_events_unique
Create Date: 2026-05-19

# Why

Per `docs/ml-architecture.md`'s degraded-mode handling ("GoPro died at
shot 47. Audio-only mode continues recording") the report needs to
distinguish a fully-instrumented session from one where some shots
have only audio coverage. Surfacing this as an explicit
`partial_session` flag (set by the post-session worker or by the
coach via PATCH /sessions/{sid}/end) is cleaner than inferring it
from per-shot diagnostic coverage in every consumer.

Default FALSE so historical sessions keep their assumed-full
semantics until a worker explicitly downgrades them.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0011_session_partial_flag"
down_revision = "0010_shot_events_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "partial_session",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "partial_session")
