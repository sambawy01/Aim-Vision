"""Session-create endpoint integration tests.

Covers POST /sessions — the coach-driven lifecycle start that
finally has a real API surface (sessions used to only exist
through test fixtures seeding directly via SQLAlchemy).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind
from app.models.tenancy import Account, Org
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


async def _seed_org(user_id: str) -> tuple[str, str]:
    """Seed an Account + Org for a user. Returns (org_id, tenant_id)."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{user_id}"
    org_id = f"org-{user_id}"
    async with sm() as s, s.begin():
        s.add(Account(id=f"acc-{user_id}", name="acc", is_active=True))
        s.add(Org(id=org_id, kind=OrgKind.solo, name="solo", tenant_id=tenant))
    return org_id, tenant


@pytest.mark.asyncio
async def test_create_session_happy_path(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "create-coach1@example.com")
    org_id, _ = await _seed_org(user_id)

    r = await client.post(
        "/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "athlete_user_id": user_id,
            "org_id": org_id,
            "discipline": "skeet",
        },
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["org_id"] == org_id
    assert out["athlete_user_id"] == user_id
    assert out["discipline"] == "skeet"
    assert out["started_at"] is not None
    assert out["ended_at"] is None
    assert out["partial_session"] is False
    assert out.get("id")


@pytest.mark.asyncio
async def test_create_session_defaults_discipline_to_trap(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "create-coach2@example.com")
    org_id, _ = await _seed_org(user_id)

    r = await client.post(
        "/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"athlete_user_id": user_id, "org_id": org_id},
    )
    assert r.status_code == 201, r.text
    assert r.json()["discipline"] == "trap"


@pytest.mark.asyncio
async def test_create_session_accepts_explicit_started_at(client: AsyncClient) -> None:
    """Offline-backfill case: client supplies a past started_at."""
    token, user_id = await _signup_and_login(client, "create-coach3@example.com")
    org_id, _ = await _seed_org(user_id)

    past = datetime(2026, 5, 1, 9, 30, tzinfo=UTC)
    r = await client.post(
        "/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "athlete_user_id": user_id,
            "org_id": org_id,
            "started_at": past.isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["started_at"].startswith("2026-05-01T09:30")


@pytest.mark.asyncio
async def test_create_session_404_when_org_missing(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "create-coach4@example.com")
    # Don't seed an org.

    r = await client.post(
        "/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"athlete_user_id": user_id, "org_id": "org-does-not-exist"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_session_404_when_athlete_missing(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "create-coach5@example.com")
    org_id, _ = await _seed_org(user_id)

    r = await client.post(
        "/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"athlete_user_id": "user-does-not-exist", "org_id": org_id},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_session_cross_tenant_org_404(client: AsyncClient) -> None:
    """Coach in tenant B cannot create a session in tenant A's org.
    404 (not 403) so the coach can't probe for other tenants' orgs."""
    _, user_a = await _signup_and_login(client, "createA@example.com")
    org_a, _ = await _seed_org(user_a)

    token_b, _ = await _signup_and_login(client, "createB@example.com")
    r = await client.post(
        "/sessions",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"athlete_user_id": user_a, "org_id": org_a},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_session_athlete_403(client: AsyncClient) -> None:
    """Athletes don't start their own sessions — coaches do."""
    _, user_id = await _signup_and_login(client, "create-coach6@example.com")
    org_id, _ = await _seed_org(user_id)

    ath_token, _ = issue_token(
        Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role="athlete")
    )
    r = await client.post(
        "/sessions",
        headers={"Authorization": f"Bearer {ath_token}"},
        json={"athlete_user_id": user_id, "org_id": org_id},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_session_appears_in_list_immediately(client: AsyncClient) -> None:
    """Round-trip sanity: POST then GET /sessions returns the new row."""
    token, user_id = await _signup_and_login(client, "create-coach7@example.com")
    org_id, _ = await _seed_org(user_id)

    cr = await client.post(
        "/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"athlete_user_id": user_id, "org_id": org_id},
    )
    assert cr.status_code == 201
    sid = cr.json()["id"]

    lr = await client.get(
        "/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert lr.status_code == 200
    ids = [s["id"] for s in lr.json()]
    assert sid in ids
