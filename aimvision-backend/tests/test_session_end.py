"""Session-end endpoint integration tests.

Covers PATCH /sessions/{sid}/end — the lifecycle close that sets
`ended_at` (idempotently) and the `partial_session` flag.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind, Session
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


async def _seed_session(user_id: str) -> str:
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{user_id}"
    sid = f"sess-{user_id}"
    async with sm() as s, s.begin():
        s.add(Account(id=f"acc-{user_id}", name="acc", is_active=True))
        s.add(Org(id=f"org-{user_id}", kind=OrgKind.solo, name="solo", tenant_id=tenant))
        s.add(
            Session(
                id=sid,
                org_id=f"org-{user_id}",
                athlete_user_id=user_id,
                started_at=datetime.now(UTC),
                tenant_id=tenant,
            )
        )
    return sid


@pytest.mark.asyncio
async def test_end_session_happy_path(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "end-coach1@example.com")
    sid = await _seed_session(user_id)

    r = await client.patch(
        f"/sessions/{sid}/end",
        headers={"Authorization": f"Bearer {token}"},
        json={"partial_session": False},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["id"] == sid
    assert out["ended_at"] is not None
    assert out["partial_session"] is False


@pytest.mark.asyncio
async def test_end_session_default_partial_is_false(client: AsyncClient) -> None:
    """Omitting `partial_session` from the payload defaults to False."""
    token, user_id = await _signup_and_login(client, "end-coach2@example.com")
    sid = await _seed_session(user_id)

    r = await client.patch(
        f"/sessions/{sid}/end",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert r.status_code == 200, r.text
    assert r.json()["partial_session"] is False


@pytest.mark.asyncio
async def test_end_session_preserves_original_ended_at(client: AsyncClient) -> None:
    """Subsequent calls keep the first ended_at — coach + worker can
    both call this endpoint and neither overwrites the lifecycle
    timestamp the other already set."""
    token, user_id = await _signup_and_login(client, "end-coach3@example.com")
    sid = await _seed_session(user_id)

    r1 = await client.patch(
        f"/sessions/{sid}/end",
        headers={"Authorization": f"Bearer {token}"},
        json={"partial_session": False},
    )
    assert r1.status_code == 200
    first_ended_at = r1.json()["ended_at"]
    assert first_ended_at is not None

    # Wait long enough that wall-clock has advanced, then call again.
    await asyncio.sleep(0.05)
    r2 = await client.patch(
        f"/sessions/{sid}/end",
        headers={"Authorization": f"Bearer {token}"},
        json={"partial_session": True},
    )
    assert r2.status_code == 200
    out = r2.json()
    assert out["ended_at"] == first_ended_at  # unchanged
    assert out["partial_session"] is True  # this DID update


@pytest.mark.asyncio
async def test_end_session_partial_flag_can_be_flipped_off_and_back_on(
    client: AsyncClient,
) -> None:
    token, user_id = await _signup_and_login(client, "end-coach4@example.com")
    sid = await _seed_session(user_id)

    for partial in (True, False, True):
        r = await client.patch(
            f"/sessions/{sid}/end",
            headers={"Authorization": f"Bearer {token}"},
            json={"partial_session": partial},
        )
        assert r.status_code == 200
        assert r.json()["partial_session"] is partial


@pytest.mark.asyncio
async def test_summary_surfaces_ended_at_and_partial_flag(client: AsyncClient) -> None:
    """GET /summary should reflect the lifecycle state after PATCH /end.
    Catches a regression where the summary forgets to surface either."""
    token, user_id = await _signup_and_login(client, "end-coach5@example.com")
    sid = await _seed_session(user_id)

    # Before end: ended_at None, partial False.
    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["ended_at"] is None
    assert out["partial_session"] is False

    # End with partial=True.
    er = await client.patch(
        f"/sessions/{sid}/end",
        headers={"Authorization": f"Bearer {token}"},
        json={"partial_session": True},
    )
    assert er.status_code == 200

    # After end: both surface in summary.
    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["ended_at"] is not None
    assert out["partial_session"] is True


@pytest.mark.asyncio
async def test_end_session_404_missing(client: AsyncClient) -> None:
    token, _ = await _signup_and_login(client, "end-coach6@example.com")
    r = await client.patch(
        "/sessions/sess-does-not-exist/end",
        headers={"Authorization": f"Bearer {token}"},
        json={"partial_session": False},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_end_session_cross_tenant_404(client: AsyncClient) -> None:
    _, user_a = await _signup_and_login(client, "endA@example.com")
    sid = await _seed_session(user_a)

    token_b, _ = await _signup_and_login(client, "endB@example.com")
    r = await client.patch(
        f"/sessions/{sid}/end",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"partial_session": False},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_end_session_athlete_403(client: AsyncClient) -> None:
    """Athletes don't end sessions — coaches and the post-session
    worker do. Athlete tier should bounce 403."""
    _, user_id = await _signup_and_login(client, "end-coach7@example.com")
    sid = await _seed_session(user_id)

    ath_token, _ = issue_token(
        Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role="athlete")
    )
    r = await client.patch(
        f"/sessions/{sid}/end",
        headers={"Authorization": f"Bearer {ath_token}"},
        json={"partial_session": False},
    )
    assert r.status_code == 403
