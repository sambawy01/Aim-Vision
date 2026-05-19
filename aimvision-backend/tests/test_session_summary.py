"""Session summary endpoint integration tests.

Covers GET /sessions/{sid}/summary — the rolled-up readiness view
the post-session UI consumes to decide between report and
"still processing".
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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


async def _set_alignment(client: AsyncClient, token: str, sid: str, rid: str) -> None:
    r = await client.patch(
        f"/sessions/{sid}/recording/{rid}/alignment",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "session_clock_offset_ns": 12_345_000,
            "session_clock_offset_confidence": 0.91,
        },
    )
    assert r.status_code == 200, r.text


def _calibration_payload(ts_ns: int = 1_700_000_000_000_000_000) -> dict[str, Any]:
    return {
        "intrinsics_k_json": [
            [1500.0, 0.0, 960.0],
            [0.0, 1500.0, 540.0],
            [0.0, 0.0, 1.0],
        ],
        "distortion_coeffs_json": [-0.05, 0.01, 0.0, 0.0, 0.0],
        "extrinsics_r_json": [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ],
        "extrinsics_t_json": [0.0, 0.0, 0.0],
        "reprojection_error_px_p95": 0.42,
        "charuco_frames_used": 12,
        "calibration_ts_ns": ts_ns,
    }


async def _post_calibration(
    client: AsyncClient, token: str, sid: str, rid: str, *, ts_ns: int = 1_700_000_000_000_000_000
) -> None:
    r = await client.post(
        f"/sessions/{sid}/recording/{rid}/calibration",
        headers={"Authorization": f"Bearer {token}"},
        json=_calibration_payload(ts_ns=ts_ns),
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_summary_empty_session_is_vacuously_complete(client: AsyncClient) -> None:
    """A session with no recordings has alignment_complete=True
    (vacuous) but calibration_complete=False (we require recordings
    to exist before declaring the session calibrated)."""
    token, user_id = await _signup_and_login(client, "sum-coach1@example.com")
    sid = await _seed_session(user_id)

    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out == {
        "session_id": sid,
        "recording_count": 0,
        "shot_count": 0,
        "calibration_count": 0,
        "alignment_complete": True,
        "calibration_complete": False,
    }


@pytest.mark.asyncio
async def test_summary_single_recording_is_trivially_aligned(client: AsyncClient) -> None:
    """A single recording is trivially aligned (it IS the master).
    Without a calibration row, calibration_complete is False."""
    token, user_id = await _signup_and_login(client, "sum-coach2@example.com")
    sid = await _seed_session(user_id)
    await _upload(client, token, sid)

    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["recording_count"] == 1
    assert out["alignment_complete"] is True
    assert out["calibration_complete"] is False


@pytest.mark.asyncio
async def test_summary_two_recordings_one_unaligned(client: AsyncClient) -> None:
    """Two recordings, only one has alignment fields set →
    alignment_complete is False."""
    token, user_id = await _signup_and_login(client, "sum-coach3@example.com")
    sid = await _seed_session(user_id)
    rid_a = await _upload(client, token, sid)
    await _upload(client, token, sid)
    await _set_alignment(client, token, sid, rid_a)

    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["recording_count"] == 2
    assert out["alignment_complete"] is False


@pytest.mark.asyncio
async def test_summary_two_recordings_both_aligned(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "sum-coach4@example.com")
    sid = await _seed_session(user_id)
    rid_a = await _upload(client, token, sid)
    rid_b = await _upload(client, token, sid)
    await _set_alignment(client, token, sid, rid_a)
    await _set_alignment(client, token, sid, rid_b)

    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["alignment_complete"] is True


@pytest.mark.asyncio
async def test_summary_calibration_complete_requires_every_recording(
    client: AsyncClient,
) -> None:
    """calibration_complete=True only when every recording in the
    session has at least one calibration. A single uncalibrated
    recording flips it to False."""
    token, user_id = await _signup_and_login(client, "sum-coach5@example.com")
    sid = await _seed_session(user_id)
    rid_a = await _upload(client, token, sid)
    rid_b = await _upload(client, token, sid)

    # Calibrate only rid_a.
    await _post_calibration(client, token, sid, rid_a, ts_ns=1_700_000_000_000_000_000)
    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["calibration_count"] == 1
    assert out["calibration_complete"] is False

    # Add a calibration for rid_b.
    await _post_calibration(client, token, sid, rid_b, ts_ns=1_700_000_010_000_000_000)
    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["calibration_count"] == 2
    assert out["calibration_complete"] is True


@pytest.mark.asyncio
async def test_summary_calibration_count_counts_rows_not_recordings(
    client: AsyncClient,
) -> None:
    """A recording can have multiple calibrations (mid-session
    recalibration trigger from §4.4). calibration_count is the row
    count; calibration_complete still flips off "≥1 per recording"."""
    token, user_id = await _signup_and_login(client, "sum-coach6@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    for ts_ns in (1_700_000_000_000_000_000, 1_700_000_010_000_000_000):
        await _post_calibration(client, token, sid, rid, ts_ns=ts_ns)

    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["recording_count"] == 1
    assert out["calibration_count"] == 2
    assert out["calibration_complete"] is True


@pytest.mark.asyncio
async def test_summary_includes_shot_count(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "sum-coach7@example.com")
    sid = await _seed_session(user_id)

    # Ingest 3 shots.
    for seq in range(3):
        r = await client.post(
            f"/sessions/{sid}/shots",
            headers={"Authorization": f"Bearer {token}"},
            json={"monotonic_seq": seq, "device_clock_ns": seq * 1_000, "shot_kind": "single"},
        )
        assert r.status_code == 201

    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["shot_count"] == 3


@pytest.mark.asyncio
async def test_summary_404_when_session_missing(client: AsyncClient) -> None:
    token, _ = await _signup_and_login(client, "sum-coach8@example.com")
    r = await client.get(
        "/sessions/sess-does-not-exist/summary",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_summary_cross_tenant_404(client: AsyncClient) -> None:
    token_a, user_a = await _signup_and_login(client, "sumA@example.com")
    sid = await _seed_session(user_a)
    await _upload(client, token_a, sid)

    token_b, _ = await _signup_and_login(client, "sumB@example.com")
    r = await client.get(
        f"/sessions/{sid}/summary",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
