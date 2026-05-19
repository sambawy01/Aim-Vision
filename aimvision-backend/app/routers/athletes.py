"""Athletes endpoints — list + read users active as athletes in the
caller's tenant.

The web dashboard + mobile coach app consume these to pick the
athlete for a new session (POST /sessions, PR #63). An "athlete"
is a User that holds at least one active Membership with role
`athlete` in the caller's tenant.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import current_principal, db_session
from ..models.tenancy import Membership, Role, User
from ..schemas.athletes import AthleteOut
from ..services.auth import Principal

router = APIRouter(prefix="/athletes", tags=["athletes"])


def _athletes_in_tenant_q(tenant_id: str) -> Select[tuple[User]]:
    """Distinct users with at least one active athlete Membership in
    the tenant. SELECT DISTINCT keeps the user list clean when an
    athlete sits in multiple cohorts/clubs in the same tenant."""
    return (
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.role == Role.athlete,
            Membership.is_active.is_(True),
        )
        .distinct()
    )


@router.get("", response_model=list[AthleteOut])
async def list_athletes(
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
) -> list[AthleteOut]:
    """All athletes (active membership, role=athlete) in the caller's
    tenant. Open to any authenticated principal in the tenant; the
    role gate is on writes (POST /sessions), not reads."""
    stmt = (
        _athletes_in_tenant_q(principal.tenant_id)
        .order_by(User.display_name.asc())
        .limit(min(max(limit, 1), 500))
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        AthleteOut(
            id=r.id,
            display_name=r.display_name,
            email=r.email,
            joined_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/{athlete_id}", response_model=AthleteOut)
async def get_athlete(
    athlete_id: str,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(db_session),
) -> AthleteOut:
    """A single athlete by id. 404 (not 403) when the user has no
    active athlete membership in the caller's tenant — that pattern
    keeps cross-tenant probing closed off."""
    stmt = _athletes_in_tenant_q(principal.tenant_id).where(User.id == athlete_id).limit(1)
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="athlete not found")
    return AthleteOut(
        id=row.id,
        display_name=row.display_name,
        email=row.email,
        joined_at=row.created_at,
    )
