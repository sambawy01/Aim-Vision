"""Unique constraint on (shot_id, event_kind, monotonic_seq) for shot_events.

Revision ID: 0010_shot_events_unique
Revises: 0009_shots_unique_session_seq
Create Date: 2026-05-19

# Why

Per ADR-0006 + the ShotEvent model docstring, multiple producers write
namespaced events to the same Shot ("audio.shot_detected",
"pose.frame_extracted", "score.hit", "diagnostic.head_tilt", ...). Each
producer maintains its own monotonic sequence — so the natural unique
key is `(shot_id, event_kind, monotonic_seq)`, not `(shot_id,
monotonic_seq)`.

At-least-once retries from any producer are idempotent against this
key. The application layer also does an idempotent-insert check, but
the unique index is what survives concurrent POSTs from two replicas
of the same producer.
"""

from __future__ import annotations

from alembic import op

revision = "0010_shot_events_unique"
down_revision = "0009_shots_unique_session_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_shot_events_shot_kind_seq",
        "shot_events",
        ["shot_id", "event_kind", "monotonic_seq"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_shot_events_shot_kind_seq", table_name="shot_events")
