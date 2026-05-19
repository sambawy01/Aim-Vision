"""Cohorts listing endpoint integration tests.

Covers GET /cohorts — tenant-scoped list with athletes_count and an
optional `org_id` filter.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind
from app.models.tenancy import Account, AthleteProfile, Cohort, Org, User
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


async def _seed_tenant_org(coach_user_id: str) -> tuple[str, str]:
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{coach_user_id}"
    org_id = f"org-{coach_user_id}"
    async with sm() as s, s.begin():
        s.add(Account(id=f"acc-{coach_user_id}", name="acc", is_active=True))
        s.add(Org(id=org_id, kind=OrgKind.solo, name="solo", tenant_id=tenant))
    return tenant, org_id


async def _seed_cohort_with_athletes(
    *, tenant: str, org_id: str, cohort_id: str, cohort_name: str, athlete_count: int
) -> None:
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s, s.begin():
        s.add(Cohort(id=cohort_id, org_id=org_id, name=cohort_name, tenant_id=tenant))
        # Athletes need a parent account + user row before AthleteProfile.
        for n in range(athlete_count):
            user_id = f"u-{cohort_id}-{n}"
            s.add(
                User(
                    id=user_id,
                    account_id=f"acc-{cohort_id}",
                    email=f"{user_id}@example.com",
                    password_hash=hash_password("pw-1234-5678"),
                    display_name=f"Athlete {n}",
                    is_active=True,
                )
            )
            s.add(
                AthleteProfile(
                    id=f"ap-{cohort_id}-{n}",
                    user_id=user_id,
                    cohort_id=cohort_id,
                    tenant_id=tenant,
                )
            )
        # One Account per cohort to satisfy the User.account_id FK.
        s.add(Account(id=f"acc-{cohort_id}", name="acc", is_active=True))


@pytest.mark.asyncio
async def test_list_cohorts_empty(client: AsyncClient) -> None:
    token, _ = await _signup_and_login(client, "coh-coach1@example.com")
    r = await client.get("/cohorts", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_cohorts_reports_athletes_count(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "coh-coach2@example.com")
    tenant, org_id = await _seed_tenant_org(user_id)
    await _seed_cohort_with_athletes(
        tenant=tenant, org_id=org_id, cohort_id="c-trap", cohort_name="Trap A", athlete_count=3
    )

    r = await client.get("/cohorts", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert len(out) == 1
    assert out[0]["id"] == "c-trap"
    assert out[0]["name"] == "Trap A"
    assert out[0]["org_id"] == org_id
    assert out[0]["athletes_count"] == 3


@pytest.mark.asyncio
async def test_list_cohorts_counts_zero_for_empty_cohort(client: AsyncClient) -> None:
    """A cohort with no athletes still appears in the list with
    athletes_count=0 — the LEFT JOIN preserves it."""
    token, user_id = await _signup_and_login(client, "coh-coach3@example.com")
    tenant, org_id = await _seed_tenant_org(user_id)
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s, s.begin():
        s.add(Cohort(id="c-empty", org_id=org_id, name="Empty Squad", tenant_id=tenant))

    r = await client.get("/cohorts", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    out = r.json()
    assert len(out) == 1
    assert out[0]["athletes_count"] == 0


@pytest.mark.asyncio
async def test_list_cohorts_orders_by_name(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "coh-coach4@example.com")
    tenant, org_id = await _seed_tenant_org(user_id)
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s, s.begin():
        s.add(Cohort(id="c-z", org_id=org_id, name="Z Squad", tenant_id=tenant))
        s.add(Cohort(id="c-a", org_id=org_id, name="A Squad", tenant_id=tenant))

    r = await client.get("/cohorts", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    names = [c["name"] for c in r.json()]
    assert names == ["A Squad", "Z Squad"]


@pytest.mark.asyncio
async def test_list_cohorts_org_id_filter(client: AsyncClient) -> None:
    """`?org_id=X` filters to a specific org. Cohorts in other orgs
    in the same tenant are hidden."""
    token, user_id = await _signup_and_login(client, "coh-coach5@example.com")
    tenant, org_id = await _seed_tenant_org(user_id)
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    other_org = f"other-{user_id}"
    async with sm() as s, s.begin():
        s.add(Org(id=other_org, kind=OrgKind.club, name="Other Club", tenant_id=tenant))
        s.add(Cohort(id="c-here", org_id=org_id, name="Local Squad", tenant_id=tenant))
        s.add(Cohort(id="c-other", org_id=other_org, name="Other Squad", tenant_id=tenant))

    r = await client.get(
        f"/cohorts?org_id={org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert len(out) == 1
    assert out[0]["id"] == "c-here"


@pytest.mark.asyncio
async def test_list_cohorts_excludes_other_tenants(client: AsyncClient) -> None:
    _, user_a = await _signup_and_login(client, "cohA@example.com")
    tenant_a, org_a = await _seed_tenant_org(user_a)
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s, s.begin():
        s.add(Cohort(id="c-A", org_id=org_a, name="Tenant A Squad", tenant_id=tenant_a))

    token_b, _ = await _signup_and_login(client, "cohB@example.com")
    r = await client.get("/cohorts", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    assert r.json() == []
