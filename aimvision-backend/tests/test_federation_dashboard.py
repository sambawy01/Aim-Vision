"""Sprint 4 EPIC 4.5 federation dashboard API tests.

Backend pair to the web `/app/federation` route (PR #38). Each test
seeds a federation Org + clubs + cohorts + sessions directly via the
ORM and asserts the wire shape consumed by `services/federation.ts`.

Wire convention: response keys are camelCase, declared via explicit
`Field(serialization_alias=...)` on each field + `response_model_by_alias=True`
on the route. The tests check camelCase keys explicitly so a regression
in any single alias is caught.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import (
    AthleteProfile,
    Cohort,
    Membership,
    Org,
    OrgKind,
    Role,
    Session,
    User,
)
from app.services.auth import Principal, issue_token

# Conventional federation tenant_id. Matches the Org.id so that
# `_resolve_federation_org` finds the row deterministically.
FED_ID = "fed-egypt-shooting"


def _token(role: str, *, user_id: str = "user-fed-admin", tenant_id: str = FED_ID) -> str:
    tok, _ = issue_token(Principal(user_id=user_id, tenant_id=tenant_id, role=role))
    return tok


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_federation(
    *,
    clubs: int = 0,
    athletes_per_club: int = 0,
    sessions_per_athlete: int = 0,
    cohorts: int = 0,
    sessions_age_days: int = 1,
) -> None:
    """Build a federation with N clubs, M athletes per club, K sessions
    per athlete in the last `sessions_age_days` days. All rows live under
    `tenant_id = FED_ID` so the federation_admin principal can see them.
    """
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    now = datetime.now(UTC)
    started_at = now - timedelta(days=sessions_age_days)

    async with sm() as s, s.begin():
        # Federation Org itself.
        s.add(
            Org(
                id=FED_ID,
                kind=OrgKind.federation,
                name="Egypt Shooting Federation",
                tenant_id=FED_ID,
                federation_id=None,
            )
        )
        # An account + an admin user (so FK constraints have something to
        # point at if we wanted to add memberships later).
        from app.models.tenancy import Account

        s.add(Account(id="acc-fed", name="Federation account", is_active=True))

        # Talent cohorts attached to the federation Org.
        cohort_ids: list[str] = []
        for i in range(cohorts):
            cid = f"cohort-{i}"
            cohort_ids.append(cid)
            s.add(Cohort(id=cid, org_id=FED_ID, name=f"Cohort {i}", tenant_id=FED_ID))

        for c in range(clubs):
            club_id = f"club-{c}"
            s.add(
                Org(
                    id=club_id,
                    kind=OrgKind.club,
                    name=f"Club {c}",
                    tenant_id=FED_ID,
                    federation_id=FED_ID,
                )
            )

            # One coach per club so the coaches_count > 0 path is
            # exercised at least once.
            coach_uid = f"u-coach-{c}"
            s.add(
                User(
                    id=coach_uid,
                    account_id="acc-fed",
                    email=f"coach{c}@example.test",
                    password_hash="x",
                    display_name=f"Coach {c}",
                )
            )
            s.add(
                Membership(
                    id=f"mem-coach-{c}",
                    user_id=coach_uid,
                    org_id=club_id,
                    role=Role.coach,
                    is_active=True,
                    tenant_id=FED_ID,
                )
            )

            for a in range(athletes_per_club):
                ath_uid = f"u-athlete-{c}-{a}"
                s.add(
                    User(
                        id=ath_uid,
                        account_id="acc-fed",
                        email=f"ath{c}-{a}@example.test",
                        password_hash="x",
                        display_name=f"Athlete {c}-{a}",
                    )
                )
                # Athlete membership in the club.
                s.add(
                    Membership(
                        id=f"mem-ath-{c}-{a}",
                        user_id=ath_uid,
                        org_id=club_id,
                        role=Role.athlete,
                        is_active=True,
                        tenant_id=FED_ID,
                    )
                )
                # AthleteProfile: first cohort_ids round-robins athletes
                # into cohorts when cohorts > 0; otherwise no cohort.
                cohort_id = cohort_ids[a % len(cohort_ids)] if cohort_ids else None
                s.add(
                    AthleteProfile(
                        id=f"prof-{c}-{a}",
                        user_id=ath_uid,
                        cohort_id=cohort_id,
                        discipline="trap",
                        handedness="right",
                        tenant_id=FED_ID,
                    )
                )

                for k in range(sessions_per_athlete):
                    s.add(
                        Session(
                            id=f"sess-{c}-{a}-{k}",
                            org_id=club_id,
                            athlete_user_id=ath_uid,
                            started_at=started_at,
                            tenant_id=FED_ID,
                        )
                    )


@pytest.mark.asyncio
async def test_overview_empty_federation_returns_zero_baseline(client: AsyncClient) -> None:
    await _seed_federation(clubs=0, athletes_per_club=0)

    r = await client.get("/v1/federation/overview", headers=_h(_token("federation_admin")))
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["federationId"] == FED_ID
    assert body["federationName"] == "Egypt Shooting Federation"
    assert body["athletesTotal"] == 0
    assert body["clubsActive"] == 0
    assert body["sessionsLast30d"] == 0
    assert body["engagementRate"] == 0.0
    assert body["talentCohorts"] == []


@pytest.mark.asyncio
async def test_overview_aggregates_clubs_athletes_sessions(client: AsyncClient) -> None:
    await _seed_federation(
        clubs=2, athletes_per_club=3, sessions_per_athlete=2, sessions_age_days=5
    )

    r = await client.get("/v1/federation/overview", headers=_h(_token("federation_admin")))
    assert r.status_code == 200, r.text
    body = r.json()

    # 2 clubs * 3 athletes = 6 athletes; 6 athletes * 2 sessions = 12.
    assert body["athletesTotal"] == 6
    assert body["clubsActive"] == 2
    assert body["sessionsLast30d"] == 12
    # 12 sessions / 6 athletes = 2.0 sessions per athlete.
    assert body["engagementRate"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_overview_engagement_rate_zero_division_guard(client: AsyncClient) -> None:
    """Zero athletes must NOT 500 on the division. Should report 0.0."""
    await _seed_federation(clubs=1, athletes_per_club=0)

    r = await client.get("/v1/federation/overview", headers=_h(_token("federation_admin")))
    assert r.status_code == 200, r.text
    assert r.json()["engagementRate"] == 0.0


@pytest.mark.asyncio
async def test_overview_sessions_outside_window_are_excluded(client: AsyncClient) -> None:
    """Sessions older than 30 days don't count toward sessionsLast30d."""
    await _seed_federation(
        clubs=1, athletes_per_club=2, sessions_per_athlete=4, sessions_age_days=45
    )

    r = await client.get("/v1/federation/overview", headers=_h(_token("federation_admin")))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["athletesTotal"] == 2
    assert body["sessionsLast30d"] == 0
    assert body["engagementRate"] == 0.0


@pytest.mark.asyncio
async def test_overview_talent_cohorts_median_zero_for_underactive(
    client: AsyncClient,
) -> None:
    """A cohort with athletes but no recent sessions reports a median of
    0.0 — the dashboard uses this to surface under-training cohorts."""
    await _seed_federation(
        clubs=1,
        athletes_per_club=4,
        sessions_per_athlete=0,
        cohorts=2,
    )

    r = await client.get("/v1/federation/overview", headers=_h(_token("federation_admin")))
    assert r.status_code == 200, r.text
    cohorts = r.json()["talentCohorts"]
    assert len(cohorts) == 2
    assert all(c["medianSessionsPer30d"] == 0.0 for c in cohorts)
    # Cohorts are sized round-robin: 4 athletes / 2 cohorts = 2 each.
    assert sorted(c["athletesCount"] for c in cohorts) == [2, 2]


@pytest.mark.asyncio
async def test_overview_forbids_non_federation_admin(client: AsyncClient) -> None:
    """The route is gated on `federation_admin`; coach and admin must
    not see a federation's roll-up. The 403 fires BEFORE the row
    lookup so even a misconfigured tenant_id can't leak data."""
    await _seed_federation()

    for role in ("coach", "athlete", "admin"):
        r = await client.get("/v1/federation/overview", headers=_h(_token(role)))
        assert r.status_code == 403, f"role={role}: {r.text}"


@pytest.mark.asyncio
async def test_overview_unknown_federation_tenant_returns_404(client: AsyncClient) -> None:
    """A `federation_admin` whose tenant doesn't point to a federation
    Org gets a 404 — we don't fabricate a federation from thin air."""
    # No seed at all.
    r = await client.get(
        "/v1/federation/overview",
        headers=_h(_token("federation_admin", tenant_id="fed-nonexistent")),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_clubs_returns_status_classification(client: AsyncClient) -> None:
    """Three clubs covering all three status branches:
    - club-0: athletes + recent session  → active
    - club-1: athletes, no recent session → paused
    - club-2: no athletes                → pending_setup
    """
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    now = datetime.now(UTC)
    async with sm() as s, s.begin():
        from app.models.tenancy import Account

        s.add(Account(id="acc-fed", name="acc", is_active=True))
        s.add(
            Org(
                id=FED_ID,
                kind=OrgKind.federation,
                name="Egypt Shooting Federation",
                tenant_id=FED_ID,
            )
        )

        for cid, name in [("club-0", "Alpha"), ("club-1", "Beta"), ("club-2", "Gamma")]:
            s.add(
                Org(
                    id=cid,
                    kind=OrgKind.club,
                    name=name,
                    tenant_id=FED_ID,
                    federation_id=FED_ID,
                )
            )

        # club-0: one athlete + a recent session.
        s.add(
            User(
                id="u-a0",
                account_id="acc-fed",
                email="a0@x",
                password_hash="x",
                display_name="A0",
            )
        )
        s.add(
            Membership(
                id="m-a0",
                user_id="u-a0",
                org_id="club-0",
                role=Role.athlete,
                is_active=True,
                tenant_id=FED_ID,
            )
        )
        s.add(
            AthleteProfile(
                id="p-a0",
                user_id="u-a0",
                discipline="trap",
                handedness="right",
                tenant_id=FED_ID,
            )
        )
        s.add(
            Session(
                id="sess-0",
                org_id="club-0",
                athlete_user_id="u-a0",
                started_at=now - timedelta(days=2),
                tenant_id=FED_ID,
            )
        )

        # club-1: one athlete, stale session (90 days old → paused).
        s.add(
            User(
                id="u-a1",
                account_id="acc-fed",
                email="a1@x",
                password_hash="x",
                display_name="A1",
            )
        )
        s.add(
            Membership(
                id="m-a1",
                user_id="u-a1",
                org_id="club-1",
                role=Role.athlete,
                is_active=True,
                tenant_id=FED_ID,
            )
        )
        s.add(
            AthleteProfile(
                id="p-a1",
                user_id="u-a1",
                discipline="trap",
                handedness="right",
                tenant_id=FED_ID,
            )
        )
        s.add(
            Session(
                id="sess-1",
                org_id="club-1",
                athlete_user_id="u-a1",
                started_at=now - timedelta(days=90),
                tenant_id=FED_ID,
            )
        )

        # club-2: no athletes, no sessions → pending_setup.

    r = await client.get("/v1/federation/clubs", headers=_h(_token("federation_admin")))
    assert r.status_code == 200, r.text
    clubs = r.json()
    assert len(clubs) == 3
    by_name = {c["clubName"]: c for c in clubs}

    assert by_name["Alpha"]["status"] == "active"
    assert by_name["Alpha"]["athletesCount"] == 1
    assert by_name["Alpha"]["lastSessionAt"] is not None

    assert by_name["Beta"]["status"] == "paused"
    assert by_name["Beta"]["athletesCount"] == 1
    assert by_name["Beta"]["lastSessionAt"] is not None

    assert by_name["Gamma"]["status"] == "pending_setup"
    assert by_name["Gamma"]["athletesCount"] == 0
    assert by_name["Gamma"]["lastSessionAt"] is None


@pytest.mark.asyncio
async def test_clubs_excludes_other_federations(client: AsyncClient) -> None:
    """A club whose `federation_id` belongs to a *different* federation
    must not appear in this federation's list. Defense in depth on top
    of the RLS scope."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s, s.begin():
        s.add(
            Org(
                id=FED_ID,
                kind=OrgKind.federation,
                name="Egypt",
                tenant_id=FED_ID,
            )
        )
        # Club correctly parented to FED_ID.
        s.add(
            Org(
                id="club-mine",
                kind=OrgKind.club,
                name="Mine",
                tenant_id=FED_ID,
                federation_id=FED_ID,
            )
        )
        # Club with NO federation_id — orphan; must not appear here.
        s.add(
            Org(
                id="club-orphan",
                kind=OrgKind.club,
                name="Orphan",
                tenant_id=FED_ID,
                federation_id=None,
            )
        )
        # Club parented to a different federation; even within the
        # same tenant it must not appear under this federation's list.
        s.add(
            Org(
                id="club-other",
                kind=OrgKind.club,
                name="Other",
                tenant_id=FED_ID,
                federation_id="fed-other",
            )
        )

    r = await client.get("/v1/federation/clubs", headers=_h(_token("federation_admin")))
    assert r.status_code == 200, r.text
    names = [c["clubName"] for c in r.json()]
    assert names == ["Mine"]


@pytest.mark.asyncio
async def test_clubs_forbids_lower_roles(client: AsyncClient) -> None:
    await _seed_federation(clubs=1)
    for role in ("coach", "athlete", "admin"):
        r = await client.get("/v1/federation/clubs", headers=_h(_token(role)))
        assert r.status_code == 403, f"role={role}: {r.text}"
