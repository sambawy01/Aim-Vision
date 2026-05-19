"""Shot ingest endpoint integration tests.

Covers POST + GET /sessions/{sid}/shots — ADR-0006 append-only shot
events, idempotent on (session_id, monotonic_seq).
"""

from __future__ import annotations

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


def _shot(monotonic_seq: int, device_clock_ns: int = 1_000_000_000) -> dict[str, object]:
    return {
        "monotonic_seq": monotonic_seq,
        "device_clock_ns": device_clock_ns,
        "shot_kind": "single",
    }


@pytest.mark.asyncio
async def test_post_shot_happy_path(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "shot-coach1@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token}"},
        json=_shot(monotonic_seq=0, device_clock_ns=12_345_000_000),
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["session_id"] == sid
    assert out["monotonic_seq"] == 0
    assert out["device_clock_ns"] == 12_345_000_000
    assert out["shot_kind"] == "single"
    assert out["server_clock_ns"] > 0
    assert out.get("id")
    assert out.get("created_at")


@pytest.mark.asyncio
async def test_post_shot_is_idempotent_on_session_seq(client: AsyncClient) -> None:
    """Resubmitting the same (session_id, monotonic_seq) returns the
    same row id — the audio detector retries on transient failure
    and we don't want to count duplicate shots."""
    token, user_id = await _signup_and_login(client, "shot-coach2@example.com")
    sid = await _seed_session(user_id)

    r1 = await client.post(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token}"},
        json=_shot(monotonic_seq=7, device_clock_ns=1_000),
    )
    assert r1.status_code == 201, r1.text
    first_id = r1.json()["id"]
    first_server_ts = r1.json()["server_clock_ns"]

    # Resubmit with the same monotonic_seq but a different
    # device_clock_ns (a real retry would presumably re-send the
    # original payload, but the API contract should still pin the
    # row to the first write, not silently overwrite).
    r2 = await client.post(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token}"},
        json=_shot(monotonic_seq=7, device_clock_ns=99_999),
    )
    assert r2.status_code == 201, r2.text
    out = r2.json()
    assert out["id"] == first_id
    assert out["device_clock_ns"] == 1_000  # unchanged
    assert out["server_clock_ns"] == first_server_ts


@pytest.mark.asyncio
async def test_list_shots_returns_them_in_monotonic_order(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "shot-coach3@example.com")
    sid = await _seed_session(user_id)

    # POST out of order.
    for seq in (2, 0, 1):
        r = await client.post(
            f"/sessions/{sid}/shots",
            headers={"Authorization": f"Bearer {token}"},
            json=_shot(monotonic_seq=seq, device_clock_ns=seq * 1_000),
        )
        assert r.status_code == 201

    g = await client.get(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert g.status_code == 200
    seqs = [s["monotonic_seq"] for s in g.json()]
    assert seqs == [0, 1, 2]


@pytest.mark.asyncio
async def test_list_shots_empty_when_none_ingested(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "shot-coach4@example.com")
    sid = await _seed_session(user_id)

    r = await client.get(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_post_shot_404_when_session_missing(client: AsyncClient) -> None:
    token, _ = await _signup_and_login(client, "shot-coach5@example.com")
    r = await client.post(
        "/sessions/sess-does-not-exist/shots",
        headers={"Authorization": f"Bearer {token}"},
        json=_shot(monotonic_seq=0),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_shot_cross_tenant_404(client: AsyncClient) -> None:
    """Coach in tenant B cannot ingest shots into a session in tenant
    A. 404, not 403, to avoid leaking session existence."""
    _, user_a = await _signup_and_login(client, "shotA@example.com")
    sid = await _seed_session(user_a)

    token_b, _ = await _signup_and_login(client, "shotB@example.com")
    r = await client.post(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token_b}"},
        json=_shot(monotonic_seq=0),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_shot_athlete_403(client: AsyncClient) -> None:
    """Athlete tier cannot POST shots directly. The on-device
    detector running under a coach-tier service-account does it
    instead — the contract is enforced at the role gate."""
    _, user_id = await _signup_and_login(client, "shot-coach6@example.com")
    sid = await _seed_session(user_id)

    ath_token, _ = issue_token(
        Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role="athlete")
    )
    r = await client.post(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {ath_token}"},
        json=_shot(monotonic_seq=0),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_post_shot_rejects_negative_monotonic_seq(client: AsyncClient) -> None:
    """`monotonic_seq < 0` is a likely producer bug — surface as 422
    rather than persisting and breaking the ordering invariant."""
    token, user_id = await _signup_and_login(client, "shot-coach7@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token}"},
        json={"monotonic_seq": -1, "device_clock_ns": 1_000, "shot_kind": "single"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_shot_default_kind_is_single(client: AsyncClient) -> None:
    """Omitting `shot_kind` falls back to "single" per the trap
    discipline convention."""
    token, user_id = await _signup_and_login(client, "shot-coach8@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token}"},
        json={"monotonic_seq": 0, "device_clock_ns": 1_000},
    )
    assert r.status_code == 201, r.text
    assert r.json()["shot_kind"] == "single"


@pytest.mark.asyncio
async def test_list_shots_cross_tenant_404(client: AsyncClient) -> None:
    """Coach in tenant B cannot list shots from tenant A's session."""
    token_a, user_a = await _signup_and_login(client, "shotlistA@example.com")
    sid = await _seed_session(user_a)
    r1 = await client.post(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token_a}"},
        json=_shot(monotonic_seq=0),
    )
    assert r1.status_code == 201

    token_b, _ = await _signup_and_login(client, "shotlistB@example.com")
    r = await client.get(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
