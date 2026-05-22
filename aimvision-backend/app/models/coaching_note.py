"""CoachingNote — persisted structured coaching note for a session.

The post-session LLM pipeline (aimvision_ml.llm) generates a
structured note conforming to docs/llm-coaching-notes-schema.md and
POSTs it here. Multiple notes per session are allowed (regeneration
on a later model / re-verification); the GET endpoint returns the
most recent. The full structured note is stored in `note_json`;
selected fields are denormalized into columns for list views and
filtering without parsing the blob.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class CoachingNote(Base, TimestampMixin, TenantScopedMixin):
    """One generated coaching note for a session."""

    __tablename__ = "coaching_notes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalized fields (mirrors of note_json) for list/filtering.
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    tone_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    verifier_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    degraded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence_overall: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # Producer's generation timestamp (distinct from created_at = DB insert).
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The full structured note (docs/llm-coaching-notes-schema.md).
    note_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
