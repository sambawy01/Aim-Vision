"""Camera-calibration endpoint integration tests.

Covers POST + GET /sessions/{sid}/recording/{rid}/calibration —
multi-camera-sync-spec.md §4.5's persistence layer.
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


def _calibration_payload(
    fx: float = 1500.0, ts_ns: int = 1_700_000_000_000_000_000
) -> dict[str, Any]:
    """Build a syntactically valid calibration payload. The values
    don't have to correspond to a real camera; the endpoint only
    enforces shape, not physical plausibility."""
    return {
        "intrinsics_k_json": [
            [fx, 0.0, 960.0],
            [0.0, fx, 540.0],
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


@pytest.mark.asyncio
async def test_post_calibration_happy_path(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "cal-coach1@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    payload = _calibration_payload()
    r = await client.post(
        f"/sessions/{sid}/recording/{rid}/calibration",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["session_id"] == sid
    assert out["recording_id"] == rid
    assert out["intrinsics_k_json"] == payload["intrinsics_k_json"]
    assert out["distortion_coeffs_json"] == payload["distortion_coeffs_json"]
    assert out["extrinsics_r_json"] == payload["extrinsics_r_json"]
    assert out["extrinsics_t_json"] == payload["extrinsics_t_json"]
    assert out["reprojection_error_px_p95"] == pytest.approx(0.42)
    assert out["charuco_frames_used"] == 12
    assert out["calibration_ts_ns"] == payload["calibration_ts_ns"]
    assert out.get("id")


@pytest.mark.asyncio
async def test_get_returns_latest_calibration_after_recalibration(
    client: AsyncClient,
) -> None:
    """Two calibrations posted; GET returns the one with the higher
    calibration_ts_ns. Mirrors spec §4.4's mid-session recalibration
    trigger semantics."""
    token, user_id = await _signup_and_login(client, "cal-coach2@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    first = _calibration_payload(fx=1500.0, ts_ns=1_700_000_000_000_000_000)
    second = _calibration_payload(fx=1505.0, ts_ns=1_700_000_010_000_000_000)
    for payload in (first, second):
        r = await client.post(
            f"/sessions/{sid}/recording/{rid}/calibration",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        assert r.status_code == 201

    g = await client.get(
        f"/sessions/{sid}/recording/{rid}/calibration",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert g.status_code == 200
    out = g.json()
    assert out["intrinsics_k_json"][0][0] == pytest.approx(1505.0)
    assert out["calibration_ts_ns"] == second["calibration_ts_ns"]


@pytest.mark.asyncio
async def test_get_404_when_no_calibration_written(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "cal-coach3@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    r = await client.get(
        f"/sessions/{sid}/recording/{rid}/calibration",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_cross_tenant_404(client: AsyncClient) -> None:
    token_a, user_a = await _signup_and_login(client, "calA@example.com")
    sid = await _seed_session(user_a)
    rid = await _upload(client, token_a, sid)

    token_b, _ = await _signup_and_login(client, "calB@example.com")
    r = await client.post(
        f"/sessions/{sid}/recording/{rid}/calibration",
        headers={"Authorization": f"Bearer {token_b}"},
        json=_calibration_payload(),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_athlete_403(client: AsyncClient) -> None:
    coach_token, user_id = await _signup_and_login(client, "cal-coach4@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, coach_token, sid)

    ath_token, _ = issue_token(
        Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role="athlete")
    )
    r = await client.post(
        f"/sessions/{sid}/recording/{rid}/calibration",
        headers={"Authorization": f"Bearer {ath_token}"},
        json=_calibration_payload(),
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_post_rejects_non_3x3_intrinsics(client: AsyncClient) -> None:
    """K matrix must be exactly 3x3 — a 2x3 input should 422."""
    token, user_id = await _signup_and_login(client, "cal-coach5@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    bad = _calibration_payload()
    bad["intrinsics_k_json"] = [[1500.0, 0.0, 960.0], [0.0, 1500.0, 540.0]]
    r = await client.post(
        f"/sessions/{sid}/recording/{rid}/calibration",
        headers={"Authorization": f"Bearer {token}"},
        json=bad,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_rejects_wrong_distortion_length(client: AsyncClient) -> None:
    """Distortion must be exactly 5-vec; the canonical Brown-Conrady
    layout. A 4-vec is a likely caller bug worth surfacing as 422."""
    token, user_id = await _signup_and_login(client, "cal-coach6@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    bad = _calibration_payload()
    bad["distortion_coeffs_json"] = [0.0, 0.0, 0.0, 0.0]
    r = await client.post(
        f"/sessions/{sid}/recording/{rid}/calibration",
        headers={"Authorization": f"Bearer {token}"},
        json=bad,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_rejects_wrong_translation_length(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "cal-coach7@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    bad = _calibration_payload()
    bad["extrinsics_t_json"] = [0.0, 0.0]  # 2-vec
    r = await client.post(
        f"/sessions/{sid}/recording/{rid}/calibration",
        headers={"Authorization": f"Bearer {token}"},
        json=bad,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_404_when_recording_not_in_session(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "cal-coach8@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/recording/rec-does-not-exist/calibration",
        headers={"Authorization": f"Bearer {token}"},
        json=_calibration_payload(),
    )
    assert r.status_code == 404
