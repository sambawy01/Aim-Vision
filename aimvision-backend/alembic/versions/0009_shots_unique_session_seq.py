"""Unique constraint on (session_id, monotonic_seq) for the shots table.

Revision ID: 0009_shots_unique_session_seq
Revises: 0008_camera_calibrations
Create Date: 2026-05-19

# Why

ADR-0006 makes shots append-only; the source-of-truth invariant the
audio shot detector + downstream ML pipeline rely on is that
`(session_id, monotonic_seq)` uniquely identifies a shot within a
session. Without a DB-level constraint, an at-least-once delivery
retry from the detector would silently create duplicate shots and
the downstream ShotEvent stream would double-count.

The application layer also does an idempotent-insert check, but the
DB index is the only thing that survives a concurrent POST race.
"""

from __future__ import annotations

from alembic import op

revision = "0009_shots_unique_session_seq"
down_revision = "0008_camera_calibrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_shots_session_seq",
        "shots",
        ["session_id", "monotonic_seq"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_shots_session_seq", table_name="shots")
