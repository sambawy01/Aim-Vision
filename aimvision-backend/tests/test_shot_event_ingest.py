"""ShotEvent ingest endpoint integration tests.

Covers POST + GET /sessions/{sid}/shots/{shot_id}/events — the
append-only per-shot event stream from ADR-0006. Multiple producers
write namespaced events to the same Shot.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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


async def _ingest_shot(client: AsyncClient, token: str, sid: str, monotonic_seq: int = 0) -> str:
    r = await client.post(
        f"/sessions/{sid}/shots",
        headers={"Authorization": f"Bearer {token}"},
        json={"monotonic_seq": monotonic_seq, "device_clock_ns": 1_000, "shot_kind": "single"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _event(
    event_kind: str = "audio.shot_detected",
    monotonic_seq: int = 0,
    *,
    produced_at: datetime | None = None,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    if produced_at is None:
        produced_at = datetime(2026, 5, 19, tzinfo=UTC)
    if payload is None:
        payload = {"confidence": 0.92, "sample_offset": 12345}
    return {
        "event_kind": event_kind,
        "monotonic_seq": monotonic_seq,
        "payload": payload,
        "produced_at": produced_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_post_shot_event_happy_path(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "ev-coach1@example.com")
    sid = await _seed_session(user_id)
    shot_id = await _ingest_shot(client, token, sid)

    r = await client.post(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token}"},
        json=_event(payload={"confidence": 0.92, "sample_offset": 4_321}),
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["shot_id"] == shot_id
    assert out["event_kind"] == "audio.shot_detected"
    assert out["monotonic_seq"] == 0
    assert out["payload"] == {"confidence": 0.92, "sample_offset": 4_321}
    assert out.get("id")
    assert out.get("created_at")
    assert out.get("produced_at")


@pytest.mark.asyncio
async def test_post_shot_event_is_idempotent(client: AsyncClient) -> None:
    """Resubmitting the same (shot_id, event_kind, monotonic_seq)
    returns the same row id — at-least-once producers can safely
    retry without double-writing."""
    token, user_id = await _signup_and_login(client, "ev-coach2@example.com")
    sid = await _seed_session(user_id)
    shot_id = await _ingest_shot(client, token, sid)

    payload1 = _event(payload={"confidence": 0.92})
    r1 = await client.post(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token}"},
        json=payload1,
    )
    assert r1.status_code == 201, r1.text
    first_id = r1.json()["id"]

    # Resubmit with a different payload to confirm the original is
    # preserved (no silent overwrite).
    payload2 = _event(payload={"confidence": 0.01, "tampered": True})
    r2 = await client.post(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token}"},
        json=payload2,
    )
    assert r2.status_code == 201
    out = r2.json()
    assert out["id"] == first_id
    assert out["payload"] == {"confidence": 0.92}


@pytest.mark.asyncio
async def test_post_shot_event_namespaced_kinds_coexist(client: AsyncClient) -> None:
    """Different producers writing with different `event_kind`s can
    share the same monotonic_seq value (it's scoped per-kind)."""
    token, user_id = await _signup_and_login(client, "ev-coach3@example.com")
    sid = await _seed_session(user_id)
    shot_id = await _ingest_shot(client, token, sid)

    for kind in ("audio.shot_detected", "pose.frame_extracted", "score.hit"):
        r = await client.post(
            f"/sessions/{sid}/shots/{shot_id}/events",
            headers={"Authorization": f"Bearer {token}"},
            json=_event(event_kind=kind, monotonic_seq=0),
        )
        assert r.status_code == 201, r.text

    g = await client.get(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert g.status_code == 200
    kinds = sorted(e["event_kind"] for e in g.json())
    assert kinds == ["audio.shot_detected", "pose.frame_extracted", "score.hit"]


@pytest.mark.asyncio
async def test_list_shot_events_orders_by_produced_at(client: AsyncClient) -> None:
    """Producer-side ordering — `produced_at` is what determines the
    list order, not insertion order or DB created_at."""
    token, user_id = await _signup_and_login(client, "ev-coach4@example.com")
    sid = await _seed_session(user_id)
    shot_id = await _ingest_shot(client, token, sid)

    base = datetime(2026, 5, 19, tzinfo=UTC)
    # POST out-of-order: 3rd-produced first, then 1st, then 2nd.
    for seq, produced_at_offset in [(2, 30), (0, 0), (1, 15)]:
        await client.post(
            f"/sessions/{sid}/shots/{shot_id}/events",
            headers={"Authorization": f"Bearer {token}"},
            json=_event(
                event_kind="audio.shot_detected",
                monotonic_seq=seq,
                produced_at=base + timedelta(seconds=produced_at_offset),
            ),
        )

    g = await client.get(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert g.status_code == 200
    seqs = [e["monotonic_seq"] for e in g.json()]
    assert seqs == [0, 1, 2]


@pytest.mark.asyncio
async def test_list_shot_events_empty_when_none_appended(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "ev-coach5@example.com")
    sid = await _seed_session(user_id)
    shot_id = await _ingest_shot(client, token, sid)

    r = await client.get(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_post_shot_event_404_when_shot_missing(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "ev-coach6@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/shots/shot-does-not-exist/events",
        headers={"Authorization": f"Bearer {token}"},
        json=_event(),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_shot_event_404_on_session_shot_mismatch(client: AsyncClient) -> None:
    """A real shot id POSTed under the wrong session id is 404 — the
    compound (shot, session, tenant) lookup catches that the shot
    doesn't belong to that session."""
    token, user_id = await _signup_and_login(client, "ev-coach7@example.com")
    sid_a = await _seed_session(user_id)
    shot_id = await _ingest_shot(client, token, sid_a)

    # Seed a second session for the same user.
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{user_id}"
    sid_b = f"sess-other-{user_id}"
    async with sm() as s, s.begin():
        s.add(
            Session(
                id=sid_b,
                org_id=f"org-{user_id}",
                athlete_user_id=user_id,
                started_at=datetime.now(UTC),
                tenant_id=tenant,
            )
        )

    r = await client.post(
        f"/sessions/{sid_b}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token}"},
        json=_event(),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_shot_event_cross_tenant_404(client: AsyncClient) -> None:
    token_a, user_a = await _signup_and_login(client, "evA@example.com")
    sid = await _seed_session(user_a)
    shot_id = await _ingest_shot(client, token_a, sid)

    token_b, _ = await _signup_and_login(client, "evB@example.com")
    r = await client.post(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token_b}"},
        json=_event(),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_shot_event_athlete_403(client: AsyncClient) -> None:
    coach_token, user_id = await _signup_and_login(client, "ev-coach8@example.com")
    sid = await _seed_session(user_id)
    shot_id = await _ingest_shot(client, coach_token, sid)

    ath_token, _ = issue_token(
        Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role="athlete")
    )
    r = await client.post(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {ath_token}"},
        json=_event(),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_post_shot_event_rejects_empty_kind(client: AsyncClient) -> None:
    """`event_kind` must be at least 1 char — an empty string is
    almost certainly a producer bug."""
    token, user_id = await _signup_and_login(client, "ev-coach9@example.com")
    sid = await _seed_session(user_id)
    shot_id = await _ingest_shot(client, token, sid)

    bad = _event()
    bad["event_kind"] = ""
    r = await client.post(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token}"},
        json=bad,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_shot_event_rejects_negative_monotonic_seq(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "ev-coach10@example.com")
    sid = await _seed_session(user_id)
    shot_id = await _ingest_shot(client, token, sid)

    bad = _event()
    bad["monotonic_seq"] = -1
    r = await client.post(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token}"},
        json=bad,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_shot_events_cross_tenant_404(client: AsyncClient) -> None:
    token_a, user_a = await _signup_and_login(client, "evlistA@example.com")
    sid = await _seed_session(user_a)
    shot_id = await _ingest_shot(client, token_a, sid)
    r1 = await client.post(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token_a}"},
        json=_event(),
    )
    assert r1.status_code == 201

    token_b, _ = await _signup_and_login(client, "evlistB@example.com")
    r = await client.get(
        f"/sessions/{sid}/shots/{shot_id}/events",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
