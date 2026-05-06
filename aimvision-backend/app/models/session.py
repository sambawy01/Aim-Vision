"""Session, Recording, Shot — capture-side domain."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class Session(Base, TimestampMixin, TenantScopedMixin):
    """A coaching session capture; container for shots and recordings."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    athlete_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    discipline: Mapped[str] = mapped_column(String(64), nullable=False, default="trap")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Recording(Base, TimestampMixin, TenantScopedMixin):
    """A media recording attached to a session (S3 object)."""

    __tablename__ = "recordings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    storage_uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upload_state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")


class Shot(Base, TimestampMixin, TenantScopedMixin):
    """An immutable shot event (ADR-0006: append-only)."""

    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    monotonic_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    device_clock_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    server_clock_ns: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shot_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="single")
