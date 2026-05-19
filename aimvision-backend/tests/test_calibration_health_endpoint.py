"""Calibration-health endpoint integration tests.

Covers GET /sessions/{sid}/recording/{rid}/calibration/health — the
multi-camera-sync-spec.md §4.4 mid-session recalibration trigger.
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
from app.schemas.camera_calibration import RECALIBRATION_TRIGGER_RATIO
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
    *, reprojection: float = 0.42, ts_ns: int = 1_700_000_000_000_000_000
) -> dict[str, Any]:
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
        "reprojection_error_px_p95": reprojection,
        "charuco_frames_used": 12,
        "calibration_ts_ns": ts_ns,
    }


async def _post_calibration(
    client: AsyncClient,
    token: str,
    sid: str,
    rid: str,
    *,
    reprojection: float,
    ts_ns: int,
) -> str:
    r = await client.post(
        f"/sessions/{sid}/recording/{rid}/calibration",
        headers={"Authorization": f"Bearer {token}"},
        json=_calibration_payload(reprojection=reprojection, ts_ns=ts_ns),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_health_single_calibration_ratio_is_one(client: AsyncClient) -> None:
    """With only one calibration row, baseline == latest and the ratio
    is 1.0. The operator does not get prompted to recalibrate."""
    token, user_id = await _signup_and_login(client, "calh-coach1@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    cal_id = await _post_calibration(
        client, token, sid, rid, reprojection=0.5, ts_ns=1_700_000_000_000_000_000
    )

    r = await client.get(
        f"/sessions/{sid}/recording/{rid}/calibration/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["recording_id"] == rid
    assert out["baseline_calibration_id"] == cal_id
    assert out["latest_calibration_id"] == cal_id
    assert out["baseline_error_px_p95"] == pytest.approx(0.5)
    assert out["latest_error_px_p95"] == pytest.approx(0.5)
    assert out["ratio_to_baseline"] == pytest.approx(1.0)
    assert out["recalibration_recommended"] is False
    assert out["recalibration_trigger_ratio"] == pytest.approx(RECALIBRATION_TRIGGER_RATIO)


@pytest.mark.asyncio
async def test_health_below_threshold_does_not_trigger(client: AsyncClient) -> None:
    """latest/baseline < 2.0 → no recalibration prompt."""
    token, user_id = await _signup_and_login(client, "calh-coach2@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    await _post_calibration(
        client, token, sid, rid, reprojection=0.5, ts_ns=1_700_000_000_000_000_000
    )
    await _post_calibration(
        client, token, sid, rid, reprojection=0.9, ts_ns=1_700_000_010_000_000_000
    )

    r = await client.get(
        f"/sessions/{sid}/recording/{rid}/calibration/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["ratio_to_baseline"] == pytest.approx(1.8)
    assert out["recalibration_recommended"] is False


@pytest.mark.asyncio
async def test_health_at_threshold_triggers(client: AsyncClient) -> None:
    """latest/baseline == 2.0 → trigger fires (inclusive boundary).
    Spec §4.4 wording is `>2x`; we treat the threshold inclusively
    so the operator gets the prompt at the boundary value too."""
    token, user_id = await _signup_and_login(client, "calh-coach3@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    await _post_calibration(
        client, token, sid, rid, reprojection=0.5, ts_ns=1_700_000_000_000_000_000
    )
    await _post_calibration(
        client, token, sid, rid, reprojection=1.0, ts_ns=1_700_000_010_000_000_000
    )

    r = await client.get(
        f"/sessions/{sid}/recording/{rid}/calibration/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["ratio_to_baseline"] == pytest.approx(2.0)
    assert out["recalibration_recommended"] is True


@pytest.mark.asyncio
async def test_health_above_threshold_triggers(client: AsyncClient) -> None:
    """latest 5x the baseline → recalibration recommended."""
    token, user_id = await _signup_and_login(client, "calh-coach4@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    baseline_id = await _post_calibration(
        client, token, sid, rid, reprojection=0.4, ts_ns=1_700_000_000_000_000_000
    )
    latest_id = await _post_calibration(
        client, token, sid, rid, reprojection=2.0, ts_ns=1_700_000_020_000_000_000
    )

    r = await client.get(
        f"/sessions/{sid}/recording/{rid}/calibration/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["baseline_calibration_id"] == baseline_id
    assert out["latest_calibration_id"] == latest_id
    assert out["baseline_error_px_p95"] == pytest.approx(0.4)
    assert out["latest_error_px_p95"] == pytest.approx(2.0)
    assert out["ratio_to_baseline"] == pytest.approx(5.0)
    assert out["recalibration_recommended"] is True


@pytest.mark.asyncio
async def test_health_picks_oldest_as_baseline_not_first_inserted(
    client: AsyncClient,
) -> None:
    """Baseline = lowest `calibration_ts_ns`, not insertion order.

    Workers can backfill calibrations out of order; the spec §4.4
    trigger compares the *latest* (chronologically) against the
    *earliest* (chronologically), regardless of write order.
    """
    token, user_id = await _signup_and_login(client, "calh-coach5@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    # Insert the newer one first.
    newer_id = await _post_calibration(
        client, token, sid, rid, reprojection=1.5, ts_ns=1_700_000_020_000_000_000
    )
    older_id = await _post_calibration(
        client, token, sid, rid, reprojection=0.5, ts_ns=1_700_000_000_000_000_000
    )

    r = await client.get(
        f"/sessions/{sid}/recording/{rid}/calibration/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["baseline_calibration_id"] == older_id
    assert out["latest_calibration_id"] == newer_id
    assert out["ratio_to_baseline"] == pytest.approx(3.0)
    assert out["recalibration_recommended"] is True


@pytest.mark.asyncio
async def test_health_404_when_no_calibration_written(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "calh-coach6@example.com")
    sid = await _seed_session(user_id)
    rid = await _upload(client, token, sid)

    r = await client.get(
        f"/sessions/{sid}/recording/{rid}/calibration/health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_health_cross_tenant_404(client: AsyncClient) -> None:
    """Cross-tenant access returns 404 (not 403) — same pattern as
    the rest of the recording endpoints."""
    token_a, user_a = await _signup_and_login(client, "calhA@example.com")
    sid = await _seed_session(user_a)
    rid = await _upload(client, token_a, sid)
    await _post_calibration(
        client, token_a, sid, rid, reprojection=0.4, ts_ns=1_700_000_000_000_000_000
    )

    token_b, _ = await _signup_and_login(client, "calhB@example.com")
    r = await client.get(
        f"/sessions/{sid}/recording/{rid}/calibration/health",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
