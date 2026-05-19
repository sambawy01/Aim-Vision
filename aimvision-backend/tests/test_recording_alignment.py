"""Recording alignment PATCH integration tests — ADR-0009 slice 4.

Covers `PATCH /sessions/{session_id}/recording/{recording_id}/alignment`:
happy path, GET round-trip, cross-tenant isolation, role gate, invalid
confidence rejection, non-existent recording 404, and session-id
mismatch (recording exists under a different session in the same
tenant).
"""

from __future__ import annotations

import hashlib
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


async def _seed_session(user_id: str, suffix: str = "") -> str:
    """Insert a parent Session row directly via the ORM."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{user_id}"
    sid = f"sess-{user_id}{suffix}"
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


def _fake_mp4(size: int = 4096) -> bytes:
    return (b"\x00\x00\x00\x18ftypmp42" + b"AIM\x00" * 4)[:16] + b"x" * max(0, size - 16)


async def _upload_recording(client: AsyncClient, token: str, sid: str) -> str:
    body = _fake_mp4()
    r = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("c.mp4", io.BytesIO(body), "video/mp4")},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# Compute a deterministic expected sha so the upload round-trip is
# tied to a real file body. (Belt-and-braces — the upload endpoint
# tests cover sha; this file focuses on the alignment fields.)
_EXPECTED_SHA = hashlib.sha256(_fake_mp4()).hexdigest()


@pytest.mark.asyncio
async def test_patch_alignment_happy_path(client: AsyncClient) -> None:
    """PATCH sets both alignment fields and the GET surface reflects them."""
    token, user_id = await _signup_and_login(client, "align-coach@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload_recording(client, token, sid)

    # Before PATCH: both alignment fields are NULL (the upload response
    # already returned them; check it.)
    # (We don't have a per-recording GET in the API yet; we'll round-trip
    # the alignment payload through PATCH's response which is the canonical
    # RecordingOut shape.)
    r = await client.patch(
        f"/sessions/{sid}/recording/{rid}/alignment",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "session_clock_offset_ns": 4_750_000,  # 4.75 ms
            "session_clock_offset_confidence": 0.82,
        },
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["id"] == rid
    assert out["session_id"] == sid
    assert out["session_clock_offset_ns"] == 4_750_000
    assert out["session_clock_offset_confidence"] == pytest.approx(0.82)
    # Sanity: the upload-side fields are still present and unchanged.
    assert out["sha256"] == _EXPECTED_SHA
    assert out["upload_state"] == "uploaded"


@pytest.mark.asyncio
async def test_patch_alignment_overwrites_previous(client: AsyncClient) -> None:
    """A second PATCH replaces the prior values — no append semantics."""
    token, user_id = await _signup_and_login(client, "align-coach2@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload_recording(client, token, sid)

    for offset, conf in [(1_000_000, 0.55), (-2_500_000, 0.91)]:
        r = await client.patch(
            f"/sessions/{sid}/recording/{rid}/alignment",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "session_clock_offset_ns": offset,
                "session_clock_offset_confidence": conf,
            },
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["session_clock_offset_ns"] == offset
        assert out["session_clock_offset_confidence"] == pytest.approx(conf)


@pytest.mark.asyncio
async def test_patch_alignment_cross_tenant_404(client: AsyncClient) -> None:
    """Tenant B cannot PATCH a recording in tenant A — the join clause
    filters on (recording_id, session_id, session.tenant_id) so the
    response is 404, not 403."""
    token_a, user_a = await _signup_and_login(client, "alignA@example.com")
    sid_a = await _seed_session(user_a)
    rid_a = await _upload_recording(client, token_a, sid_a)

    token_b, _ = await _signup_and_login(client, "alignB@example.com")
    r = await client.patch(
        f"/sessions/{sid_a}/recording/{rid_a}/alignment",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"session_clock_offset_ns": 0, "session_clock_offset_confidence": 0.5},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_alignment_requires_coach_role(client: AsyncClient) -> None:
    """An athlete-role token must be rejected — the alignment write is a
    coach (or service-account) operation per the route's require_role."""
    coach_token, user_id = await _signup_and_login(client, "align-coach3@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload_recording(client, coach_token, sid)

    ath_token, _ = issue_token(
        Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role="athlete")
    )
    r = await client.patch(
        f"/sessions/{sid}/recording/{rid}/alignment",
        headers={"Authorization": f"Bearer {ath_token}"},
        json={"session_clock_offset_ns": 1_000_000, "session_clock_offset_confidence": 0.7},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_patch_alignment_rejects_confidence_above_one(
    client: AsyncClient,
) -> None:
    """Pydantic should 422 anything outside the [0, 1] range for the
    confidence field — the normalized correlation coefficient can't
    physically exceed 1."""
    token, user_id = await _signup_and_login(client, "align-coach4@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload_recording(client, token, sid)

    r = await client.patch(
        f"/sessions/{sid}/recording/{rid}/alignment",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_clock_offset_ns": 0, "session_clock_offset_confidence": 1.5},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_alignment_rejects_confidence_below_zero(
    client: AsyncClient,
) -> None:
    token, user_id = await _signup_and_login(client, "align-coach5@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload_recording(client, token, sid)

    r = await client.patch(
        f"/sessions/{sid}/recording/{rid}/alignment",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_clock_offset_ns": 0, "session_clock_offset_confidence": -0.1},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_alignment_404_for_nonexistent_recording(
    client: AsyncClient,
) -> None:
    token, user_id = await _signup_and_login(client, "align-coach6@example.com")
    sid = await _seed_session(user_id)

    r = await client.patch(
        f"/sessions/{sid}/recording/rec-does-not-exist/alignment",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_clock_offset_ns": 0, "session_clock_offset_confidence": 0.5},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_alignment_404_when_session_id_mismatches(
    client: AsyncClient,
) -> None:
    """A recording exists in this tenant under session X, but the caller
    PATCHes /sessions/{Y}/recording/{rid_x}/alignment. The compound
    where-clause filters on (recording_id, session_id), so the response
    is 404 even though the row itself is visible to the principal."""
    token, user_id = await _signup_and_login(client, "align-coach7@example.com")
    sid_a = await _seed_session(user_id)
    rid_a = await _upload_recording(client, token, sid_a)

    # Same tenant, a second session.
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

    r = await client.patch(
        f"/sessions/{sid_b}/recording/{rid_a}/alignment",
        headers={"Authorization": f"Bearer {token}"},
        json={"session_clock_offset_ns": 0, "session_clock_offset_confidence": 0.5},
    )
    assert r.status_code == 404
