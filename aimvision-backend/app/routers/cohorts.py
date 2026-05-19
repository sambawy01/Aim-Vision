"""Cohort listing endpoint.

Stand-alone counterpart to the federation-overview cohort grid.
Returns cohorts in the caller's tenant, with an optional `org_id`
filter for club-coach UIs that only want their own org's squads.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import current_principal, db_session
from ..models.tenancy import AthleteProfile, Cohort
from ..schemas.cohorts import CohortOut
from ..services.auth import Principal

router = APIRouter(prefix="/cohorts", tags=["cohorts"])


@router.get("", response_model=list[CohortOut])
async def list_cohorts(
    org_id: str | None = Query(default=None, description="Filter to a specific org id."),
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[CohortOut]:
    """List cohorts in the caller's tenant.

    Each row carries an `athletes_count` computed from the
    `athlete_profiles.cohort_id` join. The federation dashboard's
    embedded TalentCohortOut also exposes a count, but it uses
    `medianSessionsPer30d` derived metrics — this endpoint stays
    minimal so coaches can pick a cohort without the federation-
    wide aggregations.

    Open to any authenticated principal in the tenant — read-side
    pattern matches /athletes + /orgs.
    """
    count_q = (
        select(
            Cohort.id,
            Cohort.name,
            Cohort.org_id,
            Cohort.tenant_id,
            func.count(AthleteProfile.id).label("athletes_count"),
        )
        .join(
            AthleteProfile,
            AthleteProfile.cohort_id == Cohort.id,
            isouter=True,
        )
        .where(Cohort.tenant_id == principal.tenant_id)
        .group_by(Cohort.id, Cohort.name, Cohort.org_id, Cohort.tenant_id)
        .order_by(Cohort.name.asc())
    )
    if org_id is not None:
        count_q = count_q.where(Cohort.org_id == org_id)

    rows = (await db.execute(count_q)).all()
    return [
        CohortOut(
            id=r.id,
            name=r.name,
            org_id=r.org_id,
            tenant_id=r.tenant_id,
            athletes_count=int(r.athletes_count),
        )
        for r in rows
    ]
