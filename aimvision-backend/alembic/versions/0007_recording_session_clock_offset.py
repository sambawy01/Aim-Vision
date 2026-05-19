"""Add recordings.session_clock_offset_ns + confidence — phone-capture slice 4.

Revision ID: 0007_recording_session_clock_offset
Revises: 0006_recording_source_kind
Create Date: 2026-05-19

ADR-0009 slice 4 ships the audio cross-correlation alignment algorithm
in `aimvision_ml.inference.audio_xcorr`. Its output is a per-recording
nanosecond offset relative to the session's master recording (and the
normalized-correlation confidence of that offset). This migration adds
the columns the Temporal post-session pipeline writes into once the
xcorr driver has finished processing the multi-camera audio streams.

Both columns are NULL by default — NULL means either "this is the
master recording" or "alignment hasn't been computed yet". The
PATCH endpoint at `/v1/sessions/{id}/recording/{rid}/alignment` is
how the Temporal worker (or a coach running a manual recalibration)
sets them.

The two columns travel together: setting one without the other would
leave the row in a half-aligned state that downstream consumers
would have to guard against. The API layer enforces atomicity; the
schema just stores them.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0007_recording_session_clock_offset"
down_revision = "0006_recording_source_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recordings",
        sa.Column(
            "session_clock_offset_ns",
            sa.BigInteger(),
            nullable=True,
            comment=(
                "Signed nanosecond offset of this recording's clock relative "
                "to the session's master recording, as measured by audio "
                "cross-correlation per docs/multi-camera-sync-spec.md §3.2. "
                "NULL = master OR alignment not yet computed."
            ),
        ),
    )
    op.add_column(
        "recordings",
        sa.Column(
            "session_clock_offset_confidence",
            sa.Float(),
            nullable=True,
            comment=(
                "Normalized cross-correlation coefficient in [0, 1] from "
                "audio_xcorr.PairAlignment. Higher is more confident; "
                "real cross-camera blasts land in 0.5-0.95. NULL when "
                "the offset has not yet been computed."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("recordings", "session_clock_offset_confidence")
    op.drop_column("recordings", "session_clock_offset_ns")
