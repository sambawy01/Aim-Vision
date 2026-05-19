"""CameraCalibration model — per multi-camera-sync-spec.md §4.5.

Persists the output of the
`aimvision_ml.inference.{camera_calibration,charuco_detect}` pipeline:
the ChArUco-derived intrinsic + extrinsic parameters of one camera
in one session. Multiple rows per recording are allowed so a
mid-session recalibration (spec §4.4) doesn't overwrite the prior
calibration — consumers read the most-recent row.

Matrix payloads are JSON (3x3 nested list for `K` and `R`, flat list
for `distortion` and `t`). The shape contract is enforced at the
pydantic schema layer; the ORM layer just stores the blob.
"""

from __future__ import annotations

from sqlalchemy import JSON, BigInteger, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class CameraCalibration(Base, TimestampMixin, TenantScopedMixin):
    """One calibration reading for a Recording (camera * session)."""

    __tablename__ = "camera_calibrations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    recording_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("recordings.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Matrix payloads. The pydantic layer validates shapes:
    # K (3x3), distortion (5,), R (3x3), t (3,).
    intrinsics_k_json: Mapped[list[list[float]]] = mapped_column(JSON, nullable=False)
    distortion_coeffs_json: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    extrinsics_r_json: Mapped[list[list[float]]] = mapped_column(JSON, nullable=False)
    extrinsics_t_json: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    # P95 reprojection error in pixels — the spec §4.4 mid-session
    # recalibration trigger watches this against the per-session baseline.
    reprojection_error_px_p95: Mapped[float] = mapped_column(Float, nullable=False)
    # How many ChArUco frames contributed. Reported back to operators.
    charuco_frames_used: Mapped[int] = mapped_column(Integer, nullable=False)
    # Wall-clock ns at which the calibration was computed. Distinct
    # from the row's `created_at` because the post-session worker may
    # backfill calibration rows for old recordings.
    calibration_ts_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # `created_at` + `updated_at` come from TimestampMixin.
