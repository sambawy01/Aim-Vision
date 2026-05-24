"""POST /auth/exchange — GoTrue JWT → AIMVISION session (ADR-0010).

Companion to test_auth_gotrue_verifier.py (which covers the
verification primitive). This file covers the *endpoint integration*:
the AUTH_PROVIDER flag, the gotrue_sub lookup, the
inactive-user/unknown-user 401s, and the LoginOut response shape.
"""

from __future__ import annotations

import time

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app import config
from app.db import get_app_engine
from app.models import OrgKind
from app.models.tenancy import Account, Membership, Org, Role, User

HS_SECRET = "exchange-test-shared-secret-32-bytes-min-x"
ISSUER = "https://gotrue.test.local"
AUDIENCE = "authenticated"


@pytest.fixture(autouse=True)
def _gotrue_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flip AUTH_PROVIDER=gotrue + supply matching verifier knobs.

    The autouse + monkeypatch combo means every test in this module sees
    a gotrue-mode app; tests that need to exercise the
    stub-mode-rejects-this-endpoint path override the flag explicitly.
    """
    monkeypatch.setenv("AIMVISION_AUTH_PROVIDER", "gotrue")
    monkeypatch.setenv("AIMVISION_GOTRUE_JWT_ALG", "HS256")
    monkeypatch.setenv("AIMVISION_GOTRUE_JWT_SECRET", HS_SECRET)
    monkeypatch.setenv("AIMVISION_GOTRUE_ISSUER", ISSUER)
    monkeypatch.setenv("AIMVISION_GOTRUE_AUDIENCE", AUDIENCE)
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _mint(
    *,
    sub: str,
    secret: str = HS_SECRET,
    iss: str = ISSUER,
    aud: str = AUDIENCE,
    exp_offset: int = 3600,
    email: str = "athlete@example.com",
) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": sub,
            "iss": iss,
            "aud": aud,
            "iat": now,
            "exp": now + exp_offset,
            "email": email,
            "email_verified": True,
        },
        secret,
        algorithm="HS256",
    )


async def _seed_user(
    *,
    user_id: str = "u-gotrue-1",
    email: str = "athlete@example.com",
    gotrue_sub: str | None = "00000000-0000-0000-0000-0000000000aa",
    is_active: bool = True,
    with_solo_org: bool = True,
) -> User:
    """Create an AIMVISION user pre-linked to a GoTrue sub.

    Mirrors what the bulk-import migration script will do per ADR-0010
    on the cutover day for every existing user.
    """
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s, s.begin():
        account = Account(name="solo-account")
        s.add(account)
        await s.flush()
        user = User(
            id=user_id,
            account_id=account.id,
            email=email,
            password_hash="$pbkdf2$unused-for-this-flow$0$0",
            display_name="Test Athlete",
            is_active=is_active,
            gotrue_sub=gotrue_sub,
        )
        s.add(user)
        if with_solo_org:
            s.add(
                Org(
                    kind=OrgKind.solo,
                    name="Test Athlete (solo)",
                    tenant_id=f"solo:{user_id}",
                )
            )
        await s.flush()
        return user


@pytest.mark.asyncio
async def test_exchange_returns_login_out_for_a_linked_user(client: AsyncClient) -> None:
    user = await _seed_user()
    token = _mint(sub=user.gotrue_sub or "")  # narrowing: seed sets it

    r = await client.post("/auth/exchange", json={"gotrue_jwt": token})
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["principal"]["user_id"] == user.id
    assert body["principal"]["tenant_id"] == f"solo:{user.id}"
    assert body["principal"]["display_name"] == "Test Athlete"
    # Solo membership is always present.
    tenant_ids = [m["tenant_id"] for m in body["memberships"]]
    assert f"solo:{user.id}" in tenant_ids


@pytest.mark.asyncio
async def test_exchange_picks_highest_privilege_membership(client: AsyncClient) -> None:
    """A user with both an athlete solo + an admin club membership should
    receive a token bound to the admin tenant, mirroring /auth/login."""
    user = await _seed_user(user_id="u-multi-role")
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s, s.begin():
        s.add(Org(id="org-club-1", kind=OrgKind.club, name="Demo Club", tenant_id="club-demo"))
        await s.flush()
        s.add(
            Membership(
                user_id=user.id,
                org_id="org-club-1",
                role=Role.admin,
                tenant_id="club-demo",
                is_active=True,
            )
        )

    token = _mint(sub=user.gotrue_sub or "")
    r = await client.post("/auth/exchange", json={"gotrue_jwt": token})
    assert r.status_code == 200, r.text
    assert r.json()["principal"]["tenant_id"] == "club-demo"
    assert r.json()["principal"]["role"] == "admin"


@pytest.mark.asyncio
async def test_exchange_unknown_sub_is_401(client: AsyncClient) -> None:
    # No user seeded; the JWT is otherwise valid.
    token = _mint(sub="00000000-0000-0000-0000-deadbeefcafe")
    r = await client.post("/auth/exchange", json={"gotrue_jwt": token})
    assert r.status_code == 401
    # Failure-mode opacity: the body should NOT distinguish "bad token"
    # from "unknown user" — both surface the same generic message.
    assert r.json()["error"] == "invalid identity token"


@pytest.mark.asyncio
async def test_exchange_inactive_user_is_401(client: AsyncClient) -> None:
    user = await _seed_user(user_id="u-inactive", is_active=False)
    token = _mint(sub=user.gotrue_sub or "")
    r = await client.post("/auth/exchange", json={"gotrue_jwt": token})
    assert r.status_code == 401
    assert r.json()["error"] == "invalid identity token"


@pytest.mark.asyncio
async def test_exchange_invalid_signature_is_401(client: AsyncClient) -> None:
    await _seed_user()
    token = _mint(
        sub="00000000-0000-0000-0000-0000000000aa",
        secret="not-the-real-secret-also-32-bytes-min-xx",
    )
    r = await client.post("/auth/exchange", json={"gotrue_jwt": token})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_exchange_expired_token_is_401(client: AsyncClient) -> None:
    user = await _seed_user()
    token = _mint(sub=user.gotrue_sub or "", exp_offset=-60)
    r = await client.post("/auth/exchange", json={"gotrue_jwt": token})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_exchange_wrong_audience_is_401(client: AsyncClient) -> None:
    """Service-role tokens (aud=service_role) must never produce an
    end-user session. The verifier rejects them, the endpoint returns 401."""
    user = await _seed_user()
    token = _mint(sub=user.gotrue_sub or "", aud="service_role")
    r = await client.post("/auth/exchange", json={"gotrue_jwt": token})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_exchange_404_when_auth_provider_is_stub(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the deployment is still on the legacy stub path, the endpoint
    must be operationally invisible — a 404, not a 405/403 — so a port
    scan can't tell GoTrue is wired up at all."""
    monkeypatch.setenv("AIMVISION_AUTH_PROVIDER", "stub")
    config.get_settings.cache_clear()

    user = await _seed_user()
    token = _mint(sub=user.gotrue_sub or "")
    r = await client.post("/auth/exchange", json={"gotrue_jwt": token})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_exchange_malformed_token_payload_is_422(client: AsyncClient) -> None:
    """Missing / wrong-shape body validates before we ever hit verification."""
    r = await client.post("/auth/exchange", json={})
    assert r.status_code == 422
    r = await client.post("/auth/exchange", json={"gotrue_jwt": "x"})  # below min_length
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_exchange_does_not_touch_stub_login_path(client: AsyncClient) -> None:
    """Sanity: the legacy stub login still works alongside the new endpoint
    in this test environment (auth_provider=gotrue toggles only the
    exchange endpoint's gate; stub /auth/login is independent until the
    follow-up deprecation PR)."""
    # Direct DB write of a stub-auth user (with a password we know).
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s, s.begin():
        existing = (
            (await s.execute(select(User).where(User.email == "stub@example.com")))
            .scalars()
            .first()
        )
        if existing is None:
            account = Account(name="stub-account")
            s.add(account)
            await s.flush()
            from app.services.auth import hash_password

            s.add(
                User(
                    account_id=account.id,
                    email="stub@example.com",
                    password_hash=hash_password("p4ssw0rd!1234"),
                    display_name="Stub User",
                )
            )

    r = await client.post(
        "/auth/login",
        json={"email": "stub@example.com", "password": "p4ssw0rd!1234"},
    )
    # Login may 401 because no solo org was seeded for this user, but
    # critically the route is *not* 404'd (i.e. the stub path still exists).
    assert r.status_code != 404
