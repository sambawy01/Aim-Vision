"""Session, Recording, Shot, ShotEvent — capture-side domain."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class RecordingSourceKind(enum.StrEnum):
    """Which camera backend produced this Recording. Per ADR-0009 the
    `phone_dev` value flags internally-captured footage that must NOT
    be admitted to production model gates without per-device
    calibration sign-off."""

    hero13 = "hero13"
    phone_dev = "phone_dev"
    mock = "mock"


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
    # Camera-to-server clock skew at recording start, in milliseconds. Used to
    # translate `Shot.device_clock_ns` into a real wall-clock for multi-camera
    # alignment and audit. Sprint 4 EPIC 4.1 explicitly baked this into the
    # schema now — moved up from Sprint 17 per the Embedded review.
    camera_clock_offset_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Which camera backend produced this file. Per ADR-0009: phone_dev
    # is dev-only and must be filtered out of production aggregates.
    source_kind: Mapped[RecordingSourceKind] = mapped_column(
        SAEnum(RecordingSourceKind, name="recording_source_kind"),
        nullable=False,
        default=RecordingSourceKind.hero13,
        server_default="hero13",
    )


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


class ShotEvent(Base, TimestampMixin, TenantScopedMixin):
    """Append-only event stream attached to a Shot. Per ADR-0006 the Shot itself
    is immutable; every analysis output, audio/pose annotation, or scoring update
    is a new ShotEvent row. This is the source of truth that downstream
    materialized views (post-session report, longitudinal analytics) project off.

    `event_kind` keeps the wire format open: "audio.shot_detected",
    "pose.frame_extracted", "score.hit", "score.miss", "diagnostic.head_tilt",
    "annotation.coach_note", ... Producers MUST namespace their events.
    """

    __tablename__ = "shot_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    shot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("shots.id", ondelete="CASCADE"), nullable=False
    )
    event_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    # Producer's monotonic sequence. Lets a consumer detect gaps without
    # trusting wall-clock ordering across producers.
    monotonic_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Free-form JSON. Schema is per-event-kind and lives in the producer.
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    produced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
