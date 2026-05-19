"""Add recordings.source_kind discriminator — Sprint 4 ADR-0009 slice 2.

Revision ID: 0006_recording_source_kind
Revises: 0005_active_learning_queue
Create Date: 2026-05-19

Discriminator for which camera backend produced the Recording. Lets the
reporting / model-gate pipelines filter out dev-mode phone captures
from any aggregate that would be shown to a customer or admitted as
production training data. Per ADR-0009, phone-dev recordings must never
flow into production model gates without explicit per-device
calibration sign-off.

Values:
    hero13     -- production GoPro Hero 13 footage (default)
    phone_dev  -- internal dev-mode phone capture
    mock       -- fixture / synthetic data from aimvision-camera-mock
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_recording_source_kind"
down_revision = "0005_active_learning_queue"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    source_kind = sa.Enum("hero13", "phone_dev", "mock", name="recording_source_kind")
    if _is_postgres():
        source_kind.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "recordings",
        sa.Column(
            "source_kind",
            source_kind,
            nullable=False,
            server_default="hero13",
        ),
    )
    op.create_index(
        "ix_recordings_source_kind",
        "recordings",
        ["source_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_recordings_source_kind", table_name="recordings")
    op.drop_column("recordings", "source_kind")

    if _is_postgres():
        op.execute("DROP TYPE IF EXISTS recording_source_kind")
