"""Session listing / read endpoints (scaffolds)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import current_principal, db_session
from ..models.session import Session as SessionModel
from ..schemas.session import SessionOut
from ..services.auth import Principal

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
    limit: int = 50,
) -> list[SessionOut]:
    stmt = (
        select(SessionModel)
        .where(SessionModel.tenant_id == principal.tenant_id)
        .order_by(SessionModel.started_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    result = await session.execute(stmt)
    return [SessionOut.model_validate(row) for row in result.scalars().all()]


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: str,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
) -> SessionOut:
    stmt = select(SessionModel).where(
        SessionModel.id == session_id,
        SessionModel.tenant_id == principal.tenant_id,
    )
    result = await session.execute(stmt)
    row = result.scalars().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    return SessionOut.model_validate(row)
