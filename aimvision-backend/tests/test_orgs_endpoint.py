"""Orgs listing endpoint integration tests.

Covers GET /orgs — the list of orgs the principal is a member of
inside their current tenant, consumed by the web new-session form
as an org-picker.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind
from app.models.tenancy import Account, Membership, Org, Role
from app.services.auth import Principal, issue_token


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


async def _seed_org_with_membership(
    user_id: str,
    *,
    org_id: str,
    org_name: str,
    org_kind: OrgKind = OrgKind.solo,
    active: bool = True,
) -> None:
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{user_id}"
    async with sm() as s, s.begin():
        existing_acc = (await s.execute(_account_q(f"acc-{user_id}"))).scalars().first()
        if existing_acc is None:
            s.add(Account(id=f"acc-{user_id}", name="acc", is_active=True))
        s.add(Org(id=org_id, kind=org_kind, name=org_name, tenant_id=tenant))
        s.add(
            Membership(
                id=f"mem-{user_id}-{org_id}",
                user_id=user_id,
                org_id=org_id,
                role=Role.coach,
                tenant_id=tenant,
                is_active=active,
            )
        )


def _account_q(acc_id: str):
    from sqlalchemy import select

    return select(Account).where(Account.id == acc_id)


@pytest.mark.asyncio
async def test_list_orgs_empty_when_no_memberships(client: AsyncClient) -> None:
    token, _ = await _signup_and_login(client, "orgs-coach1@example.com")
    r = await client.get("/orgs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_orgs_returns_single_org(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "orgs-coach2@example.com")
    await _seed_org_with_membership(user_id, org_id="org-A", org_name="Cairo Club")

    r = await client.get("/orgs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    out = r.json()
    assert len(out) == 1
    assert out[0]["id"] == "org-A"
    assert out[0]["name"] == "Cairo Club"
    assert out[0]["kind"] == "solo"
    assert out[0]["tenant_id"] == f"solo:{user_id}"


@pytest.mark.asyncio
async def test_list_orgs_excludes_inactive_memberships(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "orgs-coach3@example.com")
    await _seed_org_with_membership(
        user_id, org_id="org-inactive", org_name="Departed Club", active=False
    )
    r = await client.get("/orgs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_orgs_orders_by_name(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "orgs-coach4@example.com")
    await _seed_org_with_membership(user_id, org_id="org-z", org_name="Z Club")
    await _seed_org_with_membership(user_id, org_id="org-a", org_name="A Club")

    r = await client.get("/orgs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    names = [o["name"] for o in r.json()]
    assert names == ["A Club", "Z Club"]


@pytest.mark.asyncio
async def test_list_orgs_excludes_other_tenants(client: AsyncClient) -> None:
    """An org in tenant A is invisible to a coach whose only
    memberships are in tenant B."""
    _, user_a = await _signup_and_login(client, "orgsA@example.com")
    await _seed_org_with_membership(user_a, org_id="org-A", org_name="Tenant A Club")

    token_b, _ = await _signup_and_login(client, "orgsB@example.com")
    r = await client.get("/orgs", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_orgs_distinct_when_user_has_multiple_memberships_same_org(
    client: AsyncClient,
) -> None:
    """A user holding multiple roles in the same org (athlete +
    coach + parent) appears as one row in the picker."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    token, user_id = await _signup_and_login(client, "orgs-multi@example.com")
    tenant = f"solo:{user_id}"
    await _seed_org_with_membership(user_id, org_id="org-multi", org_name="Multi Club")
    # Add a second active membership for the same user + same org with a different role.
    async with sm() as s, s.begin():
        s.add(
            Membership(
                id=f"mem-{user_id}-org-multi-athlete",
                user_id=user_id,
                org_id="org-multi",
                role=Role.athlete,
                tenant_id=tenant,
                is_active=True,
            )
        )

    r = await client.get("/orgs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    out = r.json()
    assert len(out) == 1
    assert out[0]["id"] == "org-multi"
