"""Login endpoint: token + principal + memberships contract.

The web client fills its auth + tenancy stores straight from this response,
so the shape (principal, memberships) and the highest-privilege selection are
load-bearing. See aimvision-web/src/services/auth.ts.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind
from app.models.tenancy import Membership, Org, Role

PASSWORD = "p4ssw0rd!1234"


async def _signup(client: AsyncClient, email: str) -> str:
    r = await client.post(
        "/auth/signup",
        json={"email": email, "password": PASSWORD, "display_name": email.split("@")[0]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _seed_membership(user_id: str, *, tenant: str, org_name: str, role: Role) -> None:
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    org_id = f"org-{tenant}"
    async with sm() as s, s.begin():
        existing = (await s.execute(select(Org).where(Org.id == org_id))).scalars().first()
        if existing is None:
            s.add(Org(id=org_id, kind=OrgKind.club, name=org_name, tenant_id=tenant))
        s.add(
            Membership(
                id=f"mem-{user_id}-{tenant}-{role.value}",
                user_id=user_id,
                org_id=org_id,
                role=role,
                tenant_id=tenant,
                is_active=True,
            )
        )


async def _login(client: AsyncClient, email: str) -> dict:
    r = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_login_returns_token_principal_and_solo_membership(client: AsyncClient) -> None:
    user_id = await _signup(client, "login-solo@example.com")
    body = await _login(client, "login-solo@example.com")

    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["principal"]["user_id"] == user_id
    assert body["principal"]["tenant_id"] == f"solo:{user_id}"
    assert body["principal"]["role"] == "athlete"
    assert body["principal"]["display_name"] == "login-solo"
    # A fresh user has exactly the implicit solo tenancy.
    assert body["memberships"] == [
        {
            "tenant_id": f"solo:{user_id}",
            "display_name": "login-solo (solo)",
            "role": "athlete",
        }
    ]


@pytest.mark.asyncio
async def test_login_mints_token_for_highest_privilege_membership(client: AsyncClient) -> None:
    user_id = await _signup(client, "login-coach@example.com")
    await _seed_membership(user_id, tenant="org:club1", org_name="Cairo Club", role=Role.coach)

    body = await _login(client, "login-coach@example.com")

    # Principal is the coach membership, not the solo athlete one.
    assert body["principal"]["role"] == "coach"
    assert body["principal"]["tenant_id"] == "org:club1"
    # Both tenancies are offered, coach first (highest privilege).
    roles = [(m["tenant_id"], m["role"]) for m in body["memberships"]]
    assert roles[0] == ("org:club1", "coach")
    assert ("solo:" + user_id, "athlete") in roles


@pytest.mark.asyncio
async def test_login_collapses_multiple_roles_in_one_tenant_to_highest(
    client: AsyncClient,
) -> None:
    user_id = await _signup(client, "login-multi@example.com")
    await _seed_membership(user_id, tenant="org:club2", org_name="Alex Club", role=Role.athlete)
    await _seed_membership(user_id, tenant="org:club2", org_name="Alex Club", role=Role.coach)

    body = await _login(client, "login-multi@example.com")

    club_entries = [m for m in body["memberships"] if m["tenant_id"] == "org:club2"]
    assert len(club_entries) == 1
    assert club_entries[0]["role"] == "coach"


@pytest.mark.asyncio
async def test_login_wrong_password_401(client: AsyncClient) -> None:
    await _signup(client, "login-badpass@example.com")
    r = await client.post(
        "/auth/login", json={"email": "login-badpass@example.com", "password": "wrong-password-1"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email_401(client: AsyncClient) -> None:
    r = await client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert r.status_code == 401
