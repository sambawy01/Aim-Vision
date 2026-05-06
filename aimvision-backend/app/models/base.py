"""SQLAlchemy declarative base + UTC timestamp mixin."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Project-wide declarative base."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class TenantScopedMixin:
    """Marker + column for every multi-tenant table.

    `tenant_id` is a string of the form `solo:<user_id>`, `org:<org_id>`,
    `fed:<fed_id>` per docs/security/multi-tenant-isolation.md §1.
    """

    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)


def new_uuid() -> str:
    return str(uuid.uuid4())
