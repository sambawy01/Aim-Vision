"""Consent records (GDPR Art. 9 special-category data, separable per purpose)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TenantScopedMixin, TimestampMixin, new_uuid


class ConsentRecord(Base, TimestampMixin, TenantScopedMixin):
    """One row per (user, purpose, version). Revocations are new rows, not edits.

    GDPR Art. 26 (joint controllers): when a Federation and a Club both process
    the same data, both controller org IDs land in `joint_controller_org_ids`
    and the agreement reference (URL or document hash) goes in
    `joint_controller_agreement_ref`. Without this, downstream audits cannot
    answer "who consented to what processing under whose responsibility."
    """

    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose_version: Mapped[str] = mapped_column(String(32), nullable=False)
    granted: Mapped[bool] = mapped_column(nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proof_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # GDPR Art. 6 lawful-basis discriminator. Tracked separately from `granted`
    # because not every processing relies on consent (e.g. legitimate-interest
    # for security telemetry). Values: "consent", "contract",
    # "legal_obligation", "vital_interests", "public_task", "legitimate_interests".
    processing_basis: Mapped[str] = mapped_column(
        String(32), nullable=False, default="consent"
    )

    # Art. 26 joint-controller payload. JSON list of org IDs; an empty list
    # means single-controller processing under `tenant_id`.
    joint_controller_org_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    joint_controller_agreement_ref: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )

    # Forward-link to a future WithdrawalRequest (Sprint 17 right-to-erasure).
    # Nullable now; populated when a row is the cause/target of a withdrawal.
    withdrawal_request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
