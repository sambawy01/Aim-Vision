"""Federation-tier dashboard API — Sprint 4 EPIC 4.5.

Backend half of the dashboard scaffolded by PR #38. Two endpoints,
both gated by `require_role("federation_admin")`:

  GET /v1/federation/overview   — KPI card + talent cohort grid
  GET /v1/federation/clubs      — club membership table

Tenancy model used by this slice
--------------------------------

For the federation tier we adopt the convention that the federation Org
and the clubs subordinate to it share a single `tenant_id` (the
federation's). Per-club isolation at the app layer is enforced by
`Membership.org_id`; RLS still keeps other federations' rows invisible
because they live under a different `tenant_id`. The athlete `tenant_id`
on each row matches the federation, so the aggregation queries below
are single-tenant and need no cross-tenant escape hatch.

A future slice will add the federation→standalone-club traversal needed
when a club opts into a federation after-the-fact while keeping its own
tenant; see `services/authz.py::assert_can_act_as` for the placeholder.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import db_session
from ..models import AthleteProfile, Cohort, Membership, Org, OrgKind, Role, Session
from ..schemas import ClubMembershipOut, FederationOverviewOut, TalentCohortOut
from ..schemas.federation import ClubStatus
from ..services.auth import Principal
from ..services.authz import require_role

router = APIRouter(prefix="/v1/federation", tags=["federation"])

# A club is "active" if it has captured at least one session in this
# many days; otherwise "paused". "pending_setup" means the club Org row
# exists but no athletes have been registered yet.
_ACTIVE_WINDOW_DAYS = 30


async def _resolve_federation_org(session: AsyncSession, principal: Principal) -> Org:
    """Find the federation Org the principal administers.

    Convention: the federation Org's `id` equals the federation's
    `tenant_id`. If the principal's tenant doesn't map to a federation
    Org we 404 — a `federation_admin` membership must be backed by a
    real federation; the gate already rejected unauthorized roles.
    """
    stmt = select(Org).where(
        Org.id == principal.tenant_id,
        Org.kind == OrgKind.federation,
    )
    result = await session.execute(stmt)
    org = result.scalars().first()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="federation tenant has no federation Org row",
        )
    return org


async def _talent_cohorts(
    session: AsyncSession, federation_org_id: str, since: datetime
) -> list[TalentCohortOut]:
    """One row per cohort that belongs to the federation Org itself.
    Cohorts attached to subordinate clubs are aggregated under
    `athletes_total`, not here — talent cohorts are federation-level
    talent groups by definition (national team, regional development
    squad, etc.).
    """
    cohorts_stmt = select(Cohort).where(Cohort.org_id == federation_org_id)
    cohorts = (await session.execute(cohorts_stmt)).scalars().all()

    out: list[TalentCohortOut] = []
    for cohort in cohorts:
        # Athletes in cohort.
        ath_stmt = select(func.count(AthleteProfile.id)).where(
            AthleteProfile.cohort_id == cohort.id
        )
        athletes_count = int((await session.execute(ath_stmt)).scalar_one())

        # Median sessions/athlete in the last 30 days. Pull per-athlete
        # session counts; median over the resulting list. Cohorts with
        # zero athletes report 0.0.
        if athletes_count == 0:
            median_sessions = 0.0
        else:
            per_athlete_stmt = (
                select(func.count(Session.id))
                .where(
                    Session.athlete_user_id.in_(
                        select(AthleteProfile.user_id).where(AthleteProfile.cohort_id == cohort.id)
                    ),
                    Session.started_at >= since,
                )
                .group_by(Session.athlete_user_id)
            )
            counts = [int(r) for r in (await session.execute(per_athlete_stmt)).scalars().all()]
            # Athletes with zero sessions in the window are absent from the
            # group_by output. Pad to `athletes_count` so the median
            # reflects under-training cohorts honestly.
            counts.extend([0] * max(0, athletes_count - len(counts)))
            median_sessions = float(median(counts)) if counts else 0.0

        out.append(
            TalentCohortOut(
                id=cohort.id,
                name=cohort.name,
                athletes_count=athletes_count,
                median_sessions_per_30d=median_sessions,
            )
        )
    return out


@router.get(
    "/overview",
    response_model=FederationOverviewOut,
    response_model_by_alias=True,
)
async def federation_overview(
    principal: Principal = Depends(require_role(Role.federation_admin.value)),
    session: AsyncSession = Depends(db_session),
) -> FederationOverviewOut:
    fed_org = await _resolve_federation_org(session, principal)
    since = datetime.now(UTC) - timedelta(days=_ACTIVE_WINDOW_DAYS)

    athletes_stmt = select(func.count(AthleteProfile.id))
    athletes_total = int((await session.execute(athletes_stmt)).scalar_one())

    clubs_stmt = select(func.count(Org.id)).where(
        Org.kind == OrgKind.club,
        Org.federation_id == fed_org.id,
    )
    clubs_active = int((await session.execute(clubs_stmt)).scalar_one())

    sessions_stmt = select(func.count(Session.id)).where(Session.started_at >= since)
    sessions_last_30d = int((await session.execute(sessions_stmt)).scalar_one())

    engagement_rate = sessions_last_30d / athletes_total if athletes_total > 0 else 0.0

    cohorts = await _talent_cohorts(session, fed_org.id, since)

    return FederationOverviewOut(
        federation_id=fed_org.id,
        federation_name=fed_org.name,
        athletes_total=athletes_total,
        clubs_active=clubs_active,
        sessions_last_30d=sessions_last_30d,
        engagement_rate=engagement_rate,
        talent_cohorts=cohorts,
    )


def _classify_status(athletes_count: int, last_session_at: datetime | None) -> ClubStatus:
    if athletes_count == 0:
        return "pending_setup"
    if last_session_at is None:
        return "paused"
    cutoff = datetime.now(UTC) - timedelta(days=_ACTIVE_WINDOW_DAYS)
    if last_session_at.tzinfo is None:
        # SQLite returns naive datetimes; treat them as UTC for the
        # purposes of the active-window classification. Postgres returns
        # tz-aware values directly.
        last_session_at = last_session_at.replace(tzinfo=UTC)
    return "active" if last_session_at >= cutoff else "paused"


@router.get(
    "/clubs",
    response_model=list[ClubMembershipOut],
    response_model_by_alias=True,
)
async def list_federation_clubs(
    principal: Principal = Depends(require_role(Role.federation_admin.value)),
    session: AsyncSession = Depends(db_session),
) -> list[ClubMembershipOut]:
    fed_org = await _resolve_federation_org(session, principal)

    clubs_stmt = (
        select(Org)
        .where(Org.kind == OrgKind.club, Org.federation_id == fed_org.id)
        .order_by(Org.name)
    )
    clubs = (await session.execute(clubs_stmt)).scalars().all()

    out: list[ClubMembershipOut] = []
    for club in clubs:
        athletes_count = int(
            (
                await session.execute(
                    select(func.count(func.distinct(AthleteProfile.user_id))).where(
                        AthleteProfile.user_id.in_(
                            select(Membership.user_id).where(
                                Membership.org_id == club.id,
                                Membership.role == Role.athlete,
                                Membership.is_active.is_(True),
                            )
                        )
                    )
                )
            ).scalar_one()
        )
        coaches_count = int(
            (
                await session.execute(
                    select(func.count(func.distinct(Membership.user_id))).where(
                        Membership.org_id == club.id,
                        Membership.role == Role.coach,
                        Membership.is_active.is_(True),
                    )
                )
            ).scalar_one()
        )
        last_session: datetime | None = (
            await session.execute(
                select(func.max(Session.started_at)).where(Session.org_id == club.id)
            )
        ).scalar_one_or_none()
        out.append(
            ClubMembershipOut(
                club_id=club.id,
                club_name=club.name,
                athletes_count=athletes_count,
                coaches_count=coaches_count,
                last_session_at=last_session,
                status=_classify_status(athletes_count, last_session),
            )
        )
    return out
