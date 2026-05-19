"""Orgs endpoints — list orgs the caller is a member of, within
their current tenant.

The new-session form (web PR #69) will consume `GET /orgs` to render
an org-picker dropdown, replacing the temporary manual org-id text
input. Coaches who hold memberships in multiple orgs (a club coach
who is also a federation coach) can disambiguate cleanly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import current_principal, db_session
from ..models.tenancy import Membership, Org
from ..schemas.orgs import OrgOut
from ..services.auth import Principal

router = APIRouter(prefix="/orgs", tags=["orgs"])


def _user_orgs_in_tenant_q(user_id: str, tenant_id: str) -> Select[tuple[Org]]:
    """Orgs that the user has at least one active membership in,
    scoped to the caller's tenant. SELECT DISTINCT against the Org
    primary key keeps the result clean when the user has multiple
    memberships (athlete + coach + parent) in the same org."""
    return (
        select(Org)
        .join(Membership, Membership.org_id == Org.id)
        .where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
            Membership.is_active.is_(True),
            Org.tenant_id == tenant_id,
        )
        .distinct()
    )


@router.get("", response_model=list[OrgOut])
async def list_orgs(
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[OrgOut]:
    """Orgs the caller is a member of inside their current tenant,
    ordered by name. Open to any authenticated principal — the org
    list is what the UI shows in a picker; the actual write
    permissions are enforced on POST /sessions etc.
    """
    stmt = _user_orgs_in_tenant_q(principal.user_id, principal.tenant_id).order_by(Org.name.asc())
    rows = (await db.execute(stmt)).scalars().all()
    return [
        OrgOut(
            id=r.id,
            name=r.name,
            kind=r.kind.value,
            tenant_id=r.tenant_id,
            federation_id=r.federation_id,
        )
        for r in rows
    ]
