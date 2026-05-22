"""Right-to-erasure models: per-tenant DEK + erasure ledger.

Implements the load-bearing primitives of
docs/compliance/right-to-erasure-architecture.md:

  * `TenantEncryptionKey` — the per-tenant Data Encryption Key (§2).
    All tenant data at rest is encrypted under this key; destroying it
    crypto-shreds the tenant's data everywhere it lives, including in
    encrypted backups (§2.3). The wrapped DEK is stored here; the
    plaintext DEK is only ever materialized in process memory.
  * `ErasureTicket` — the append-only erasure ledger (§5.2). One row
    per erasure request, retained for accountability even after the
    data itself is shredded.

The Temporal erasure *workflow*, DSAR portal, sub-processor fan-out,
and model exclusion-list / retraining (§4-§7) are later-sprint work;
this module is the storage + crypto foundation they build on.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, new_uuid


class TenantEncryptionKey(Base):
    """The wrapped Data Encryption Key for one tenant.

    `wrapped_dek` is the DEK encrypted under the per-region KEK. When
    `shredded_at` is set the DEK is destroyed (`wrapped_dek` is NULLed)
    and the tenant's data becomes permanently undecryptable. A shredded
    row is retained as a tombstone so the DEK is never silently
    re-created (which would un-shred the data).
    """

    __tablename__ = "tenant_encryption_keys"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    key_version: Mapped[int] = mapped_column(default=1, nullable=False)
    # NULL once shredded. Format: 12-byte nonce || AES-256-GCM ciphertext.
    wrapped_dek: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    shredded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ErasureTicket(Base, TimestampMixin):
    """One erasure request in the append-only erasure ledger (§5.2).

    Retained for accountability per the GDPR Art. 5(2) obligation even
    after the subject's data is shredded — it holds pseudonymous IDs
    and the enumerated reference counts, not Article 9 data.
    """

    __tablename__ = "erasure_tickets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_uuid)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    athlete_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    # "pending" on submit -> "completed" after the shred fan-out runs.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # Enumerated reference counts captured at execution time (§5.4).
    references_json: Mapped[dict[str, int] | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
