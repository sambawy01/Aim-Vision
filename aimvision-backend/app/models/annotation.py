"""Coach annotations with explicit visibility scopes (multi-tenant-isolation §7)."""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class AnnotationVisibility(enum.StrEnum):
    private = "private"
    share_with_athlete = "share_with_athlete"
    share_with_club = "share_with_club"
    share_with_federation = "share_with_federation"


class Annotation(Base, TimestampMixin, TenantScopedMixin):
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    target_shot_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("shots.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[AnnotationVisibility] = mapped_column(
        SAEnum(AnnotationVisibility, name="annotation_visibility"),
        nullable=False,
        default=AnnotationVisibility.private,
    )
