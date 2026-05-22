"""Athlete longitudinal-progress endpoint tests.

Covers GET /athletes/{id}/progress — per-session diagnostic-atom
rates from the shot-event stream + latest-vs-baseline deltas.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind, Session
from app.models.session import Shot, ShotEvent
from app.models.tenancy import Account, Membership, Org, Role, User
from app.services.auth import Principal, hash_password, issue_token


async def _signup_and_login(client: AsyncClient, email: str) -> str:
    sr = await client.post(
        "/auth/signup",
        json={"email": email, "password": "p4ssw0rd!1234", "display_name": email.split("@")[0]},
    )
    assert sr.status_code == 201, sr.text
    uid = sr.json()["id"]
    token, _ = issue_token(Principal(user_id=uid, tenant_id=f"solo:{uid}", role="coach"))
    return token, uid


async def _seed_athlete(coach_uid: str, *, athlete_id: str) -> None:
    """Seed account/org + an athlete user with an active membership."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{coach_uid}"
    async with sm() as s, s.begin():
        s.add(Account(id=f"acc-{coach_uid}", name="acc", is_active=True))
        s.add(Org(id=f"org-{coach_uid}", kind=OrgKind.solo, name="solo", tenant_id=tenant))
        s.add(
            User(
                id=athlete_id,
                account_id=f"acc-{coach_uid}",
                email=f"{athlete_id}@example.com",
                password_hash=hash_password("athlete-pw-1234"),
                display_name="Athlete",
                is_active=True,
            )
        )
        s.add(
            Membership(
                id=f"mem-{athlete_id}",
                user_id=athlete_id,
                org_id=f"org-{coach_uid}",
                role=Role.athlete,
                tenant_id=tenant,
                is_active=True,
            )
        )


async def _seed_session_with_diagnostics(
    *,
    coach_uid: str,
    athlete_id: str,
    session_id: str,
    started_at: datetime,
    head_lift_shots: int,
    clean_shots: int,
) -> None:
    """A session with `head_lift_shots` shots flagged head_lift (prob
    0.8) and `clean_shots` shots with no atom over threshold."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{coach_uid}"
    async with sm() as s, s.begin():
        s.add(
            Session(
                id=session_id,
                org_id=f"org-{coach_uid}",
                athlete_user_id=athlete_id,
                started_at=started_at,
                tenant_id=tenant,
            )
        )
        for seq, is_head_lift in enumerate([True] * head_lift_shots + [False] * clean_shots):
            shot_id = f"{session_id}-shot-{seq}"
            s.add(
                Shot(
                    id=shot_id,
                    tenant_id=tenant,
                    session_id=session_id,
                    monotonic_seq=seq,
                    device_clock_ns=seq * 1000,
                    server_clock_ns=seq * 1000,
                    shot_kind="single",
                )
            )
            s.add(
                ShotEvent(
                    id=f"{shot_id}-diag",
                    tenant_id=tenant,
                    shot_id=shot_id,
                    event_kind="diagnostic.head_inference",
                    monotonic_seq=0,
                    payload={"head_lift": 0.8 if is_head_lift else 0.1, "stopped_gun": 0.2},
                    produced_at=started_at,
                )
            )


@pytest.mark.asyncio
async def test_progress_empty_for_athlete_with_no_sessions(client: AsyncClient) -> None:
    token, coach = await _signup_and_login(client, "prog-coach1@example.com")
    await _seed_athlete(coach, athlete_id="ath-1")
    r = await client.get("/athletes/ath-1/progress", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["athlete_id"] == "ath-1"
    assert out["sessions_analyzed"] == 0
    assert out["sessions"] == []
    assert out["deltas"] == {}


@pytest.mark.asyncio
async def test_progress_computes_per_session_rates(client: AsyncClient) -> None:
    token, coach = await _signup_and_login(client, "prog-coach2@example.com")
    await _seed_athlete(coach, athlete_id="ath-2")
    base = datetime(2026, 5, 1, tzinfo=UTC)
    # Session 1 (older): 4 of 10 head_lift -> 0.4
    await _seed_session_with_diagnostics(
        coach_uid=coach,
        athlete_id="ath-2",
        session_id="s1",
        started_at=base,
        head_lift_shots=4,
        clean_shots=6,
    )
    # Session 2 (newer): 1 of 10 head_lift -> 0.1
    await _seed_session_with_diagnostics(
        coach_uid=coach,
        athlete_id="ath-2",
        session_id="s2",
        started_at=base + timedelta(days=1),
        head_lift_shots=1,
        clean_shots=9,
    )

    r = await client.get("/athletes/ath-2/progress", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["sessions_analyzed"] == 2
    # Oldest -> newest.
    s1, s2 = out["sessions"]
    assert s1["session_id"] == "s1"
    assert s1["shot_count"] == 10
    assert s1["diagnostic_rates"]["head_lift"] == pytest.approx(0.4)
    assert s2["diagnostic_rates"]["head_lift"] == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_progress_delta_latest_vs_baseline(client: AsyncClient) -> None:
    """Two prior sessions at 0.4 and 0.2 (baseline 0.3); latest 0.1 ->
    delta -0.2 (improvement)."""
    token, coach = await _signup_and_login(client, "prog-coach3@example.com")
    await _seed_athlete(coach, athlete_id="ath-3")
    base = datetime(2026, 5, 1, tzinfo=UTC)
    await _seed_session_with_diagnostics(
        coach_uid=coach,
        athlete_id="ath-3",
        session_id="a",
        started_at=base,
        head_lift_shots=4,
        clean_shots=6,
    )
    await _seed_session_with_diagnostics(
        coach_uid=coach,
        athlete_id="ath-3",
        session_id="b",
        started_at=base + timedelta(days=1),
        head_lift_shots=2,
        clean_shots=8,
    )
    await _seed_session_with_diagnostics(
        coach_uid=coach,
        athlete_id="ath-3",
        session_id="c",
        started_at=base + timedelta(days=2),
        head_lift_shots=1,
        clean_shots=9,
    )

    r = await client.get(
        "/athletes/ath-3/progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    d = r.json()["deltas"]["head_lift"]
    assert d["current"] == pytest.approx(0.1)
    assert d["baseline"] == pytest.approx(0.3)  # mean(0.4, 0.2)
    assert d["delta_vs_baseline"] == pytest.approx(-0.2)


@pytest.mark.asyncio
async def test_progress_no_deltas_with_single_session(client: AsyncClient) -> None:
    token, coach = await _signup_and_login(client, "prog-coach4@example.com")
    await _seed_athlete(coach, athlete_id="ath-4")
    await _seed_session_with_diagnostics(
        coach_uid=coach,
        athlete_id="ath-4",
        session_id="only",
        started_at=datetime(2026, 5, 1, tzinfo=UTC),
        head_lift_shots=3,
        clean_shots=7,
    )
    r = await client.get("/athletes/ath-4/progress", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    out = r.json()
    assert out["sessions_analyzed"] == 1
    assert out["deltas"] == {}


@pytest.mark.asyncio
async def test_progress_404_for_non_athlete(client: AsyncClient) -> None:
    token, _ = await _signup_and_login(client, "prog-coach5@example.com")
    r = await client.get(
        "/athletes/nope/progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_progress_last_n_caps_window(client: AsyncClient) -> None:
    token, coach = await _signup_and_login(client, "prog-coach6@example.com")
    await _seed_athlete(coach, athlete_id="ath-6")
    base = datetime(2026, 5, 1, tzinfo=UTC)
    for i in range(3):
        await _seed_session_with_diagnostics(
            coach_uid=coach,
            athlete_id="ath-6",
            session_id=f"sx{i}",
            started_at=base + timedelta(days=i),
            head_lift_shots=1,
            clean_shots=4,
        )
    r = await client.get(
        "/athletes/ath-6/progress?last_n=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["sessions_analyzed"] == 2
    # The two most-recent sessions, oldest -> newest.
    assert [s["session_id"] for s in out["sessions"]] == ["sx1", "sx2"]
