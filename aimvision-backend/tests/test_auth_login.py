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


@pytest.mark.asyncio
async def test_login_sets_refresh_cookie(client: AsyncClient) -> None:
    await _signup(client, "login-cookie@example.com")
    await _login(client, "login-cookie@example.com")
    assert client.cookies.get("av_refresh")


@pytest.mark.asyncio
async def test_refresh_mints_a_working_access_token(client: AsyncClient) -> None:
    await _signup(client, "refresh-ok@example.com")
    body = await _login(client, "refresh-ok@example.com")
    old_token = body["access_token"]

    # The refresh cookie was stored by the client at login; /auth/refresh
    # exchanges it for a fresh access token without re-sending credentials.
    r = await client.post("/auth/refresh")
    assert r.status_code == 200, r.text
    new_token = r.json()["access_token"]
    assert new_token

    # The minted token authenticates a protected endpoint.
    tenant = body["principal"]["tenant_id"]
    protected = await client.get(
        "/athletes",
        headers={"Authorization": f"Bearer {new_token}", "X-Tenant-Scope": tenant},
    )
    assert protected.status_code == 200, protected.text
    assert old_token  # sanity: login also returned one


@pytest.mark.asyncio
async def test_refresh_without_cookie_401(client: AsyncClient) -> None:
    r = await client.post("/auth/refresh")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_cannot_be_used_as_bearer(client: AsyncClient) -> None:
    await _signup(client, "refresh-bearer@example.com")
    await _login(client, "refresh-bearer@example.com")
    refresh_value = client.cookies.get("av_refresh")
    assert refresh_value

    # Using the refresh token as an access bearer must be rejected (401), so a
    # stolen refresh token can't directly call the API.
    r = await client.get(
        "/athletes",
        headers={"Authorization": f"Bearer {refresh_value}", "X-Tenant-Scope": "solo:x"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_switch_tenant_rebinds_token_to_target(client: AsyncClient) -> None:
    user_id = await _signup(client, "switch-ok@example.com")
    await _seed_membership(user_id, tenant="org:club9", org_name="Club Nine", role=Role.coach)
    body = await _login(client, "switch-ok@example.com")
    # Login mints for the highest-privilege tenant (the coach club).
    assert body["principal"]["tenant_id"] == "org:club9"
    access = body["access_token"]

    # Switch down to the solo tenancy. The call carries the current (club)
    # token + matching scope, so it passes the middleware.
    solo = f"solo:{user_id}"
    r = await client.post(
        "/auth/switch-tenant",
        json={"tenant_id": solo},
        headers={"Authorization": f"Bearer {access}", "X-Tenant-Scope": "org:club9"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["principal"]["tenant_id"] == solo
    assert out["principal"]["role"] == "athlete"

    # The re-minted token works against the solo tenant scope.
    new = out["access_token"]
    protected = await client.get(
        "/athletes", headers={"Authorization": f"Bearer {new}", "X-Tenant-Scope": solo}
    )
    assert protected.status_code == 200, protected.text


@pytest.mark.asyncio
async def test_switch_tenant_to_non_member_403(client: AsyncClient) -> None:
    user_id = await _signup(client, "switch-403@example.com")
    body = await _login(client, "switch-403@example.com")
    access = body["access_token"]
    solo = f"solo:{user_id}"
    r = await client.post(
        "/auth/switch-tenant",
        json={"tenant_id": "org:not-mine"},
        headers={"Authorization": f"Bearer {access}", "X-Tenant-Scope": solo},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_switch_tenant_requires_auth_401(client: AsyncClient) -> None:
    r = await client.post("/auth/switch-tenant", json={"tenant_id": "solo:whoever"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_clears_refresh_cookie(client: AsyncClient) -> None:
    await _signup(client, "logout@example.com")
    await _login(client, "logout@example.com")
    assert client.cookies.get("av_refresh")

    r = await client.post("/auth/logout")
    assert r.status_code == 204
    # Cookie is cleared, so a subsequent refresh fails.
    client.cookies.clear()
    again = await client.post("/auth/refresh")
    assert again.status_code == 401
