"""Active learning queue — Sprint 6 EPIC 6.5.

Stores low-confidence or uncertainty-flagged ML outputs awaiting expert
review. The inference pipeline enqueues an item when:

  - calibrated confidence is below the per-task threshold
  - drift detector flags out-of-distribution input
  - the classical baseline and the learned model disagree
  - an annotator manually requests a re-label
  - the prediction belongs to a rare class

The annotator UI (Sprint 7) pulls pending items ordered by priority,
claims one, submits labels, then the training pipeline picks them up
on the next cycle.

The table is tenant-scoped so each Federation labels its own data;
items are never cross-tenant by design (it would leak athlete identity
through the prediction payload).
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class UncertaintySignal(enum.StrEnum):
    low_confidence = "low_confidence"
    ood_drift = "ood_drift"
    disagreement_with_classical = "disagreement_with_classical"
    rare_class = "rare_class"
    manual_flag = "manual_flag"


class ActiveLearningStatus(enum.StrEnum):
    pending = "pending"
    claimed = "claimed"
    labelled = "labelled"
    discarded = "discarded"


class ActiveLearningItem(Base, TimestampMixin, TenantScopedMixin):
    """One queue entry. The prediction payload is opaque JSON keyed by
    `model_name`; downstream training jobs reproject it according to the
    model's known output schema (kept in aimvision-ml/configs)."""

    __tablename__ = "active_learning_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    # Optional FK to a specific shot. Clip-level items (audio-only event
    # streams, multi-shot aggregates) leave this null.
    shot_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    prediction: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    uncertainty_signal: Mapped[UncertaintySignal] = mapped_column(
        SAEnum(UncertaintySignal, name="al_uncertainty_signal"), nullable=False
    )

    status: Mapped[ActiveLearningStatus] = mapped_column(
        SAEnum(ActiveLearningStatus, name="al_status"),
        nullable=False,
        default=ActiveLearningStatus.pending,
    )
    # Higher priority surfaces first. Default 0; the pipeline bumps to
    # 10+ for rare classes or OOD drift so they jump the queue.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Annotator state. Null until claimed/labelled.
    annotator_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    labelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    labels: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    # Free-text note the annotator can leave (e.g., "ambiguous - clay
    # impact arrived ~30ms after shot, audio detector confused").
    annotator_note: Mapped[str | None] = mapped_column(String(2048), nullable=True)
