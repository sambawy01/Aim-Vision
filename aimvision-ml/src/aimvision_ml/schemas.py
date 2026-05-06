"""Pydantic models for ML predictions and feature vectors.

These travel between training, inference, and registry code paths. The LLM
coaching-note schema is JSON Schema (loaded from the markdown spec); see
`aimvision_ml.llm.schema`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from aimvision_ml.taxonomy import DiagnosticCategory

Probability = Annotated[float, Field(ge=0.0, le=1.0)]


class AtomPrediction(BaseModel):
    """Single-atom calibrated probability + confidence-interval coverage."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: DiagnosticCategory
    probability: Probability
    in_conformal_set: bool = Field(
        default=False,
        description="True if this atom is in the 90%-coverage conformal prediction set.",
    )


class ShotPrediction(BaseModel):
    """Per-shot output of the multi-task hierarchical head.

    Multi-label by construction: head_lift + stopped_gun + off_line co-occur.
    Cite docs/ml-architecture.md §8 and docs/diagnostic-taxonomy.md.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    shot_id: str = Field(pattern=r"^shot_[0-9]{1,4}$")
    session_id: str
    atoms: list[AtomPrediction]
    primary: DiagnosticCategory | None = Field(
        default=None,
        description="Highest-priority atom after DAG ordering (stance → mount → swing → break).",
    )
    abstained: bool = Field(
        default=False,
        description="True if all branch experts fell below their per-class thresholds.",
    )
    model_version: str
    taxonomy_version: str
    predicted_at: datetime


class ShotFeatureVector(BaseModel):
    """Feature vector for one shot. Inputs to the diagnostic head.

    Multimodal per docs/ml-architecture.md §8: pose + IMU + audio + VideoMAE
    embedding. Per-modality availability flags let downstream code abstain
    when a signal is missing rather than trust zero-imputed features.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    shot_id: str = Field(pattern=r"^shot_[0-9]{1,4}$")
    session_id: str
    pose_keypoints: list[list[float]] | None = None  # [T, K, 3] or None
    imu_trace: list[list[float]] | None = None  # [T, 6] or None
    audio_features: list[float] | None = None
    videomae_embedding: list[float] | None = None
    pose_available: bool
    imu_available: bool
    audio_available: bool
    videomae_available: bool


class GateResult(BaseModel):
    """Outcome of the bias-audit + calibration CI gate.

    Cite docs/ml-architecture.md §13 (every model promotion runs this).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    passed: bool
    ece: float
    brier: float
    macro_f1: float
    top3_macro_f1: float
    conformal_coverage: float
    failed_axes: list[str] = Field(default_factory=list)
    notes: str = ""
