"""Right-to-erasure endpoints (GDPR Art. 17 / Egypt PDPL).

Admin-/coach-initiated erasure on behalf of a data subject (the DSAR
self-service portal is Sprint 17). The grace period is collapsed here:
`execute` runs the shred immediately. The production Temporal workflow
inserts the 30-day grace + sub-processor fan-out around these same
service calls.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import db_session
from ..models.erasure import ErasureTicket
from ..models.tenancy import Role
from ..schemas.erasure import ErasureRequestIn, ErasureTicketOut
from ..services import erasure
from ..services.auth import Principal
from ..services.authz import require_role

router = APIRouter(prefix="/erasure", tags=["erasure"])


@router.post("", response_model=ErasureTicketOut, status_code=status.HTTP_201_CREATED)
async def submit_erasure(
    payload: ErasureRequestIn,
    principal: Principal = Depends(require_role(Role.coach.value)),
    db: AsyncSession = Depends(db_session),
) -> ErasureTicketOut:
    """Open an erasure ticket for a data subject in the caller's tenant."""
    ticket = await erasure.submit_erasure(
        db,
        tenant_id=principal.tenant_id,
        athlete_user_id=payload.athlete_user_id,
        requested_by=principal.user_id,
        reason=payload.reason,
    )
    return ErasureTicketOut.model_validate(ticket)


@router.post("/{ticket_id}/execute", response_model=ErasureTicketOut)
async def execute_erasure(
    ticket_id: str,
    principal: Principal = Depends(require_role(Role.coach.value)),
    db: AsyncSession = Depends(db_session),
) -> ErasureTicketOut:
    """Fulfil the ticket: tombstone identifiers + crypto-shred the
    tenant DEK. Tenant-scoped (404 on cross-tenant or missing)."""
    try:
        ticket = await erasure.execute_erasure(
            db, ticket_id=ticket_id, tenant_id=principal.tenant_id
        )
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="erasure ticket not found") from exc
    return ErasureTicketOut.model_validate(ticket)


@router.get("/{ticket_id}", response_model=ErasureTicketOut)
async def get_erasure_ticket(
    ticket_id: str,
    principal: Principal = Depends(require_role(Role.coach.value)),
    db: AsyncSession = Depends(db_session),
) -> ErasureTicketOut:
    """Read an erasure ticket's status in the caller's tenant."""
    ticket = await db.get(ErasureTicket, ticket_id)
    if ticket is None or ticket.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="erasure ticket not found")
    return ErasureTicketOut.model_validate(ticket)
