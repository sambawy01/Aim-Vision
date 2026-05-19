"""Add camera_calibrations table — multi-camera-sync-spec.md §4.5.

Revision ID: 0008_camera_calibrations
Revises: 0007_recording_session_clock_offset
Create Date: 2026-05-19

Per-recording per-session camera calibration produced by the
`aimvision_ml.inference.camera_calibration` + `charuco_detect`
pipeline. Schema matches the spec's `CameraCalibration` struct.

# Why a separate table (not columns on Recording)

Spec §4.4 calls for mid-session recalibration when reprojection error
spikes. Storing multiple calibrations per recording over time
requires its own table; the Recording row stays the camera identity
+ media payload, calibration becomes the time-stamped reading.

# Matrix storage as JSON

Intrinsics K (3x3), distortion (5,), extrinsics R (3x3), extrinsics t
(3,) are stored as JSON arrays. The alternative (9 + 5 + 9 + 3 = 26
separate float columns) is painful in code for no real query benefit
— calibrations are read by composite primary key, not by individual
matrix entries.

The application layer enforces matrix shapes via pydantic; the DB
just stores the blobs.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0008_camera_calibrations"
down_revision = "0007_recording_session_clock_offset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "camera_calibrations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(128),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "session_id",
            sa.String(64),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recording_id",
            sa.String(64),
            sa.ForeignKey("recordings.id", ondelete="CASCADE"),
            nullable=False,
            comment=(
                "The camera identity — one calibration per camera per session, "
                "but spec §4.4 allows multiple over time for mid-session "
                "recalibration triggers."
            ),
        ),
        sa.Column(
            "intrinsics_k_json",
            sa.JSON(),
            nullable=False,
            comment="3x3 intrinsic matrix [[fx,0,cx],[0,fy,cy],[0,0,1]] as nested list.",
        ),
        sa.Column(
            "distortion_coeffs_json",
            sa.JSON(),
            nullable=False,
            comment="5-param Brown-Conrady [k1,k2,p1,p2,k3] as flat list.",
        ),
        sa.Column(
            "extrinsics_r_json",
            sa.JSON(),
            nullable=False,
            comment="3x3 rotation matrix relative to session master camera.",
        ),
        sa.Column(
            "extrinsics_t_json",
            sa.JSON(),
            nullable=False,
            comment="3-vector translation [tx,ty,tz] relative to session master camera.",
        ),
        sa.Column(
            "reprojection_error_px_p95",
            sa.Float(),
            nullable=False,
            comment=(
                "P95 reprojection error in pixels from the bundle adjustment. "
                "Spec §4.4 uses this to trigger mid-session recalibration when "
                "the value spikes > 2x baseline."
            ),
        ),
        sa.Column(
            "charuco_frames_used",
            sa.Integer(),
            nullable=False,
            comment="Number of ChArUco-detection frames that contributed to the calibration.",
        ),
        sa.Column(
            "calibration_ts_ns",
            sa.BigInteger(),
            nullable=False,
            comment="Wall-clock nanoseconds at which the calibration was computed.",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_camera_calibrations_recording_id",
        "camera_calibrations",
        ["recording_id"],
    )
    op.create_index(
        "ix_camera_calibrations_session_id",
        "camera_calibrations",
        ["session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_camera_calibrations_session_id", table_name="camera_calibrations")
    op.drop_index("ix_camera_calibrations_recording_id", table_name="camera_calibrations")
    op.drop_table("camera_calibrations")
