"""Recording GET endpoint integration tests.

Covers GET /sessions/{session_id}/recording (list) and
GET /sessions/{session_id}/recording/{recording_id} (single).

These endpoints close a real usability gap: prior to this slice the
only way to read a recording was via the upload response (POST) or
the alignment PATCH response — both inconvenient for any consumer
that wants to look at an existing recording's state, including the
alignment fields written by the Temporal worker.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind, Session
from app.models.tenancy import Account, Org
from app.services.auth import Principal, issue_token
from app.services.storage import LocalFsStorage, set_storage


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path: Path):
    set_storage(LocalFsStorage(tmp_path))
    yield tmp_path
    set_storage(None)


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


def _fake_mp4(size: int = 1024) -> bytes:
    return (b"\x00\x00\x00\x18ftypmp42" + b"AIM\x00" * 4)[:16] + b"x" * max(0, size - 16)


async def _upload(client: AsyncClient, token: str, sid: str) -> str:
    r = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("c.mp4", io.BytesIO(_fake_mp4()), "video/mp4")},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_list_returns_all_recordings_in_session(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "ls-coach1@example.com")
    sid = await _seed_session(user_id)
    rids = [await _upload(client, token, sid) for _ in range(3)]

    r = await client.get(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    listed = r.json()
    assert {row["id"] for row in listed} == set(rids)
    # `source_kind` defaults to hero13 on upload; the list response
    # carries the field unchanged.
    assert all(row["source_kind"] == "hero13" for row in listed)


@pytest.mark.asyncio
async def test_list_returns_empty_for_session_with_no_recordings(
    client: AsyncClient,
) -> None:
    token, user_id = await _signup_and_login(client, "ls-coach2@example.com")
    sid = await _seed_session(user_id)
    r = await client.get(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_cross_tenant_404(client: AsyncClient) -> None:
    """Tenant B can't list recordings in tenant A's session — the
    session lookup fails first and the response is 404."""
    token_a, user_a = await _signup_and_login(client, "lsA@example.com")
    sid = await _seed_session(user_a)
    await _upload(client, token_a, sid)

    token_b, _ = await _signup_and_login(client, "lsB@example.com")
    r = await client.get(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_single_recording_returns_alignment_fields(
    client: AsyncClient,
) -> None:
    """After a PATCH writes the alignment fields, GET surfaces them so
    a consumer can read the offset without re-running the PATCH."""
    token, user_id = await _signup_and_login(client, "get-coach1@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)
    pr = await client.patch(
        f"/sessions/{sid}/recording/{rid}/alignment",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_clock_offset_ns": 1_234_567, "session_clock_offset_confidence": 0.71},
    )
    assert pr.status_code == 200

    r = await client.get(
        f"/sessions/{sid}/recording/{rid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["id"] == rid
    assert out["session_id"] == sid
    assert out["session_clock_offset_ns"] == 1_234_567
    assert out["session_clock_offset_confidence"] == pytest.approx(0.71)


@pytest.mark.asyncio
async def test_get_single_recording_404_for_unknown_id(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "get-coach2@example.com")
    sid = await _seed_session(user_id)

    r = await client.get(
        f"/sessions/{sid}/recording/rec-does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_single_recording_cross_tenant_404(client: AsyncClient) -> None:
    token_a, user_a = await _signup_and_login(client, "getA@example.com")
    sid = await _seed_session(user_a)
    rid = await _upload(client, token_a, sid)

    token_b, _ = await _signup_and_login(client, "getB@example.com")
    r = await client.get(
        f"/sessions/{sid}/recording/{rid}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_get_single_recording_404_when_session_id_mismatches(
    client: AsyncClient,
) -> None:
    """Same recording, wrong parent-session URL → 404. Mirrors the PATCH
    endpoint's compound where-clause semantics."""
    token, user_id = await _signup_and_login(client, "get-coach3@example.com")
    sid_a = await _seed_session(user_id)
    rid_a = await _upload(client, token, sid_a)

    # Add a second session in the same tenant.
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{user_id}"
    sid_b = f"sess-{user_id}-b"
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

    r = await client.get(
        f"/sessions/{sid_b}/recording/{rid_a}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
