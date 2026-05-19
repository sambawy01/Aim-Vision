"""Camera calibration DTOs — multi-camera-sync-spec.md §4.5.

Mirrors the `CameraCalibration` Rust struct on the wire. Matrix
shapes are enforced via pydantic validators; the matching SQLAlchemy
columns store JSON blobs.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

# Pydantic v2 returns ValueErrors from field_validators by stashing them
# into `ctx['error']` of the validation-error payload. FastAPI then
# JSON-encodes the response with the ValueError instance still in
# place, which fails with `Object of type ValueError is not JSON
# serializable`. `PydanticCustomError` is the documented way to avoid
# that: it carries a structured-string-only context that round-trips
# through JSON cleanly.


def _validate_3x3(value: list[list[float]]) -> list[list[float]]:
    if len(value) != 3 or any(len(row) != 3 for row in value):
        raise PydanticCustomError(
            "shape_mismatch",
            "expected 3x3 matrix; got {rows}x{cols}",
            {
                "rows": str(len(value)),
                "cols": str(len(value[0]) if value else 0),
            },
        )
    return value


def _validate_flat_len(expected_len: int) -> Callable[[list[float]], list[float]]:
    def _v(value: list[float]) -> list[float]:
        if len(value) != expected_len:
            raise PydanticCustomError(
                "shape_mismatch",
                "expected length-{expected} vector; got {got}",
                {"expected": str(expected_len), "got": str(len(value))},
            )
        return value

    return _v


class CameraCalibrationIn(BaseModel):
    """Payload for the POST calibration endpoint. The post-session
    Temporal worker hands the bundle-adjustment output here."""

    intrinsics_k_json: list[list[float]] = Field(
        ...,
        description=("3x3 intrinsic matrix [[fx,0,cx],[0,fy,cy],[0,0,1]] as nested list."),
    )
    distortion_coeffs_json: list[float] = Field(
        ...,
        description="5-param Brown-Conrady [k1,k2,p1,p2,k3] as flat list.",
    )
    extrinsics_r_json: list[list[float]] = Field(
        ...,
        description=(
            "3x3 rotation matrix taking world points to camera frame "
            "(relative to session master camera per spec §4.5)."
        ),
    )
    extrinsics_t_json: list[float] = Field(
        ...,
        description="3-vector translation relative to session master camera.",
    )
    reprojection_error_px_p95: float = Field(
        ...,
        ge=0.0,
        description=(
            "P95 reprojection error in pixels from the bundle adjustment. "
            "Spec §4.4 mid-session recalibration trigger fires when this "
            "spikes > 2x baseline."
        ),
    )
    charuco_frames_used: int = Field(
        ...,
        ge=1,
        description="Number of ChArUco-detection frames that contributed.",
    )
    calibration_ts_ns: int = Field(
        ...,
        ge=0,
        description="Wall-clock nanoseconds at which the calibration was computed.",
    )

    @field_validator("intrinsics_k_json", "extrinsics_r_json")
    @classmethod
    def _ensure_3x3(cls, v: list[list[float]]) -> list[list[float]]:
        return _validate_3x3(v)

    @field_validator("distortion_coeffs_json")
    @classmethod
    def _ensure_len_5(cls, v: list[float]) -> list[float]:
        return _validate_flat_len(5)(v)

    @field_validator("extrinsics_t_json")
    @classmethod
    def _ensure_len_3(cls, v: list[float]) -> list[float]:
        return _validate_flat_len(3)(v)


class CameraCalibrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    recording_id: str
    intrinsics_k_json: list[list[float]]
    distortion_coeffs_json: list[float]
    extrinsics_r_json: list[list[float]]
    extrinsics_t_json: list[float]
    reprojection_error_px_p95: float
    charuco_frames_used: int
    calibration_ts_ns: int
    created_at: datetime
    updated_at: datetime


# Multi-camera-sync-spec.md §4.4: re-prompt the operator to recalibrate
# when the latest reprojection error spikes past 2x the per-recording
# baseline. The exact factor is exposed here so tests + downstream
# clients agree on the threshold.
RECALIBRATION_TRIGGER_RATIO = 2.0


class CalibrationHealthOut(BaseModel):
    """Derived health view over a recording's calibration history.

    Implements the spec §4.4 mid-session recalibration trigger:
    `recalibration_recommended` is True iff
    `latest / baseline >= RECALIBRATION_TRIGGER_RATIO`. The baseline
    is the *oldest* calibration for the recording (the first one the
    operator captured); the latest is the most-recent row.

    If only a single calibration exists, baseline == latest, the
    ratio is 1.0, and `recalibration_recommended` is False.
    """

    recording_id: str
    baseline_calibration_id: str
    latest_calibration_id: str
    baseline_error_px_p95: float
    latest_error_px_p95: float
    baseline_calibration_ts_ns: int
    latest_calibration_ts_ns: int
    ratio_to_baseline: float
    recalibration_recommended: bool
    recalibration_trigger_ratio: float = Field(
        default=RECALIBRATION_TRIGGER_RATIO,
        description=(
            "Threshold the latest/baseline ratio is compared against. "
            "Echoed so clients can render an operator-facing message "
            "without hardcoding the spec value."
        ),
    )
