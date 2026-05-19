"""Athletes endpoint integration tests.

Covers GET /athletes (list) + GET /athletes/{id}. An "athlete" is a
user with an active athlete-role Membership in the caller's tenant.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind
from app.models.tenancy import Account, Membership, Org, Role, User
from app.services.auth import Principal, hash_password, issue_token


async def _signup_and_login(
    client: AsyncClient, email: str, *, role: str = "coach"
) -> tuple[str, str]:
    sr = await client.post(
        "/auth/signup",
        json={"email": email, "password": "p4ssw0rd!1234", "display_name": email.split("@")[0]},
    )
    assert sr.status_code == 201, sr.text
    user_id = sr.json()["id"]
    token, _ = issue_token(Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role=role))
    return token, user_id


async def _ensure_tenant(coach_user_id: str) -> str:
    """Idempotent seed of Account + default Org for the coach's tenant.
    Returns the org id. Safe to call multiple times in a test that
    creates many athletes."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{coach_user_id}"
    acc_id = f"acc-{coach_user_id}"
    org_id = f"org-{coach_user_id}"
    async with sm() as s, s.begin():
        existing = (await s.execute(select(Account).where(Account.id == acc_id))).scalars().first()
        if existing is None:
            s.add(Account(id=acc_id, name="acc", is_active=True))
            s.add(Org(id=org_id, kind=OrgKind.solo, name="solo", tenant_id=tenant))
    return org_id


async def _seed_org_and_athlete(
    coach_user_id: str,
    *,
    athlete_email: str,
    athlete_name: str,
    active: bool = True,
) -> str:
    """Seed an athlete user + an athlete-role Membership in the
    coach's tenant. The Account + Org are ensured (idempotent) so
    multiple calls in a test reuse the same tenancy."""
    org_id = await _ensure_tenant(coach_user_id)
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{coach_user_id}"
    athlete_id = f"ath-{athlete_email}"
    async with sm() as s, s.begin():
        s.add(
            User(
                id=athlete_id,
                account_id=f"acc-{coach_user_id}",
                email=athlete_email,
                password_hash=hash_password("athlete-pw-1234"),
                display_name=athlete_name,
                is_active=True,
            )
        )
        s.add(
            Membership(
                id=f"mem-{athlete_id}",
                user_id=athlete_id,
                org_id=org_id,
                role=Role.athlete,
                tenant_id=tenant,
                is_active=active,
            )
        )
    return athlete_id


@pytest.mark.asyncio
async def test_list_athletes_empty_when_no_memberships(client: AsyncClient) -> None:
    token, _ = await _signup_and_login(client, "ath-coach1@example.com")

    r = await client.get("/athletes", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_athletes_returns_active_athlete_in_tenant(client: AsyncClient) -> None:
    token, coach_id = await _signup_and_login(client, "ath-coach2@example.com")
    await _seed_org_and_athlete(
        coach_id,
        athlete_email="anna.athlete@example.com",
        athlete_name="Anna Athlete",
    )

    r = await client.get("/athletes", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["display_name"] == "Anna Athlete"
    assert rows[0]["email"] == "anna.athlete@example.com"
    assert rows[0]["joined_at"] is not None


@pytest.mark.asyncio
async def test_list_athletes_excludes_inactive_memberships(client: AsyncClient) -> None:
    """A user whose athlete membership is is_active=False isn't an
    athlete from this tenant's perspective."""
    token, coach_id = await _signup_and_login(client, "ath-coach3@example.com")
    await _seed_org_and_athlete(
        coach_id,
        athlete_email="inactive.athlete@example.com",
        athlete_name="Inactive Athlete",
        active=False,
    )

    r = await client.get("/athletes", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_athletes_orders_by_display_name(client: AsyncClient) -> None:
    token, coach_id = await _signup_and_login(client, "ath-coach4@example.com")
    await _seed_org_and_athlete(
        coach_id, athlete_email="z.athlete@example.com", athlete_name="Z Athlete"
    )
    await _seed_org_and_athlete(
        coach_id, athlete_email="a.athlete@example.com", athlete_name="A Athlete"
    )

    r = await client.get("/athletes", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    names = [row["display_name"] for row in r.json()]
    assert names == ["A Athlete", "Z Athlete"]


@pytest.mark.asyncio
async def test_list_athletes_excludes_other_tenants(client: AsyncClient) -> None:
    """An athlete in tenant A doesn't appear when tenant B queries."""
    _, coach_a = await _signup_and_login(client, "athA-coach@example.com")
    await _seed_org_and_athlete(
        coach_a, athlete_email="A.athlete@example.com", athlete_name="Tenant A Athlete"
    )

    token_b, _ = await _signup_and_login(client, "athB-coach@example.com")
    r = await client.get("/athletes", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_get_athlete_happy_path(client: AsyncClient) -> None:
    token, coach_id = await _signup_and_login(client, "ath-coach5@example.com")
    athlete_id = await _seed_org_and_athlete(
        coach_id,
        athlete_email="byid.athlete@example.com",
        athlete_name="By-Id Athlete",
    )

    r = await client.get(
        f"/athletes/{athlete_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["id"] == athlete_id
    assert out["display_name"] == "By-Id Athlete"


@pytest.mark.asyncio
async def test_get_athlete_404_for_unknown_id(client: AsyncClient) -> None:
    token, _ = await _signup_and_login(client, "ath-coach6@example.com")
    r = await client.get(
        "/athletes/user-does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_athlete_404_for_cross_tenant(client: AsyncClient) -> None:
    """An athlete that exists in tenant A returns 404 when tenant B
    asks for them by id — closes off cross-tenant probing."""
    _, coach_a = await _signup_and_login(client, "athcross-A@example.com")
    athlete_id = await _seed_org_and_athlete(
        coach_a,
        athlete_email="cross.athlete@example.com",
        athlete_name="Cross-Tenant Athlete",
    )

    token_b, _ = await _signup_and_login(client, "athcross-B@example.com")
    r = await client.get(
        f"/athletes/{athlete_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_athletes_distinct_when_multiple_memberships(
    client: AsyncClient,
) -> None:
    """If an athlete has multiple memberships in the same tenant
    (cohort + club, say), the list endpoint deduplicates them — the
    same User shouldn't appear twice in the result."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    token, coach_id = await _signup_and_login(client, "ath-coach7@example.com")
    tenant = f"solo:{coach_id}"
    athlete_id = await _seed_org_and_athlete(
        coach_id,
        athlete_email="multi.athlete@example.com",
        athlete_name="Multi-Membership Athlete",
    )
    # Add a second active membership for the same user via a second org.
    async with sm() as s, s.begin():
        s.add(
            Org(
                id=f"org2-{coach_id}",
                kind=OrgKind.club,
                name="extra club",
                tenant_id=tenant,
            )
        )
        s.add(
            Membership(
                id=f"mem2-{athlete_id}",
                user_id=athlete_id,
                org_id=f"org2-{coach_id}",
                role=Role.athlete,
                tenant_id=tenant,
                is_active=True,
            )
        )

    r = await client.get("/athletes", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    # The user should appear exactly once even though they have two
    # athlete memberships.
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == athlete_id


# datetime import for type hints in helpers; explicit to keep
# the linter happy.
_ = datetime(2026, 1, 1, tzinfo=UTC)
