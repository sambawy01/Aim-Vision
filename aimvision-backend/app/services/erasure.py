"""Right-to-erasure orchestration (right-to-erasure-architecture.md §5).

A synchronous, tenant-scoped implementation of the erasure ledger +
fan-out. The production design runs this as a durable Temporal
workflow with a 30-day grace period, sub-processor fan-out, and
model exclusion-list updates (§5.1, §5.7); this slice implements the
parts that are deterministic and testable today:

  1. `submit_erasure`   — record the request in the ledger (§5.2).
  2. `enumerate_references` — inventory operational-DB references (§5.4).
  3. `execute_erasure`  — tombstone the subject's identifiers (§5.5)
     and crypto-shred the tenant DEK (§2.3), then close the ledger
     entry with the enumerated counts (§5.6).

Granularity: this shreds the *tenant* DEK, so it implements the
§2.4 tenant-level tier — erasure-of-tenant = erasure-of-account,
which is the correct semantics for the Solo tier (tenant == athlete).
Sub-tenant per-athlete erasure within a federation cohort needs the
hierarchical sub-DEK tier and is deferred.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.coaching_note import CoachingNote
from ..models.consent import ConsentRecord
from ..models.erasure import ErasureTicket
from ..models.session import Session as SessionModel
from ..models.session import Shot
from ..models.tenancy import User
from . import crypto_shred


async def submit_erasure(
    db: AsyncSession,
    *,
    tenant_id: str,
    athlete_user_id: str,
    requested_by: str,
    reason: str,
) -> ErasureTicket:
    """Open a pending erasure ticket in the ledger."""
    ticket = ErasureTicket(
        tenant_id=tenant_id,
        athlete_user_id=athlete_user_id,
        requested_by=requested_by,
        reason=reason,
        status="pending",
    )
    db.add(ticket)
    await db.flush()
    await db.refresh(ticket)
    return ticket


async def enumerate_references(
    db: AsyncSession, *, tenant_id: str, athlete_user_id: str
) -> dict[str, int]:
    """Count operational-DB references to the subject (§5.4).

    Recorded on the ledger entry as evidence of scope; the actual data
    is rendered undecryptable by the DEK shred regardless of counts.
    """
    session_ids = (
        (
            await db.execute(
                select(SessionModel.id).where(
                    SessionModel.tenant_id == tenant_id,
                    SessionModel.athlete_user_id == athlete_user_id,
                )
            )
        )
        .scalars()
        .all()
    )

    async def _count(stmt: Select[tuple[int]]) -> int:
        return int((await db.execute(stmt)).scalar_one())

    shots = 0
    coaching_notes = 0
    if session_ids:
        shots = await _count(select(func.count(Shot.id)).where(Shot.session_id.in_(session_ids)))
        coaching_notes = await _count(
            select(func.count(CoachingNote.id)).where(CoachingNote.session_id.in_(session_ids))
        )
    consent_records = await _count(
        select(func.count(ConsentRecord.id)).where(ConsentRecord.user_id == athlete_user_id)
    )

    return {
        "sessions": len(session_ids),
        "shots": shots,
        "coaching_notes": coaching_notes,
        "consent_records": consent_records,
    }


async def execute_erasure(db: AsyncSession, *, ticket_id: str, tenant_id: str) -> ErasureTicket:
    """Fulfil a pending erasure ticket (§5.4-§5.6).

    Tenant-scoped: a ticket in another tenant is invisible (the caller
    surfaces 404). Idempotent — re-executing a completed ticket returns
    it unchanged.
    """
    ticket = await db.get(ErasureTicket, ticket_id)
    if ticket is None or ticket.tenant_id != tenant_id:
        raise KeyError(ticket_id)
    if ticket.status == "completed":
        return ticket

    refs = await enumerate_references(
        db, tenant_id=tenant_id, athlete_user_id=ticket.athlete_user_id
    )

    # Tombstone the subject's direct identifiers (§5.5). Referential
    # integrity is preserved; PII is redacted to non-reversible values.
    user = await db.get(User, ticket.athlete_user_id)
    if user is not None:
        user.email = f"erased+{user.id}@erased.invalid"
        user.display_name = "erased"
        user.password_hash = "erased"
        user.is_active = False

    # Crypto-shred (§2.3): destroy the tenant DEK so all data at rest
    # (incl. encrypted backups) is permanently undecryptable.
    await crypto_shred.shred_tenant_dek(db, tenant_id)

    ticket.references_json = refs
    ticket.status = "completed"
    ticket.completed_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(ticket)
    return ticket
