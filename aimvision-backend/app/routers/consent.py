"""Consent grant / revoke endpoints (GDPR Art. 7, 9)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import current_principal, db_session
from ..models.consent import ConsentRecord
from ..schemas.consent import ConsentGrantIn, ConsentOut, ConsentRevokeIn
from ..services.auth import Principal

router = APIRouter(prefix="/consent", tags=["consent"])


@router.post("/grant", response_model=ConsentOut, status_code=status.HTTP_201_CREATED)
async def grant_consent(
    payload: ConsentGrantIn,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
) -> ConsentOut:
    record = ConsentRecord(
        tenant_id=principal.tenant_id,
        user_id=principal.user_id,
        purpose=payload.purpose,
        purpose_version=payload.purpose_version,
        granted=True,
        granted_at=datetime.now(UTC),
        proof_uri=payload.proof_uri,
    )
    session.add(record)
    await session.flush()
    return ConsentOut.model_validate(record)


@router.post("/revoke", response_model=ConsentOut)
async def revoke_consent(
    payload: ConsentRevokeIn,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
) -> ConsentOut:
    stmt = (
        select(ConsentRecord)
        .where(
            ConsentRecord.user_id == principal.user_id,
            ConsentRecord.purpose == payload.purpose,
            ConsentRecord.purpose_version == payload.purpose_version,
            ConsentRecord.granted.is_(True),
            ConsentRecord.revoked_at.is_(None),
        )
        .order_by(ConsentRecord.granted_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    record: ConsentRecord | None = result.scalars().first()
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no active consent for purpose")
    record.revoked_at = datetime.now(UTC)
    record.granted = False
    await session.flush()
    return ConsentOut.model_validate(record)
