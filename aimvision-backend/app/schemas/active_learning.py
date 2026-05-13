"""Pydantic schemas for the active learning queue."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ..models.active_learning import ActiveLearningStatus, UncertaintySignal


class ActiveLearningItemIn(BaseModel):
    """Enqueue payload from the inference pipeline."""

    session_id: str
    shot_id: str | None = None
    model_name: str = Field(..., max_length=128)
    model_version: str = Field(..., max_length=64)
    prediction: dict[str, object]
    confidence: float = Field(..., ge=0.0, le=1.0)
    uncertainty_signal: UncertaintySignal
    priority: int = Field(0, ge=0, le=100)


class ActiveLearningLabelIn(BaseModel):
    """Annotator submitting labels."""

    labels: dict[str, object]
    annotator_note: str | None = Field(None, max_length=2048)


class ActiveLearningItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    session_id: str
    shot_id: str | None
    model_name: str
    model_version: str
    prediction: dict[str, object]
    confidence: float
    uncertainty_signal: UncertaintySignal
    status: ActiveLearningStatus
    priority: int
    annotator_user_id: str | None
    claimed_at: datetime | None
    labelled_at: datetime | None
    labels: dict[str, object] | None
    annotator_note: str | None
    created_at: datetime
    updated_at: datetime
