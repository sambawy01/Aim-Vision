"""Coaching-note persistence endpoint tests.

Covers POST + GET /sessions/{sid}/coaching-note — storing the
structured LLM coaching note and reading back the most recent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
    uid = sr.json()["id"]
    token, _ = issue_token(Principal(user_id=uid, tenant_id=f"solo:{uid}", role=role))
    return token, uid


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


def _note(
    session_id: str,
    *,
    headline: str = "Solid session — head lift on the left stations is the next fix.",
    verifier_passed: bool = True,
    degraded: bool = False,
    generated_at: str = "2026-05-21T05:41:37+00:00",
) -> dict[str, Any]:
    """A structured coaching note matching the schema's required keys."""
    top = (
        []
        if not verifier_passed
        else [
            {
                "category": "head_lift",
                "confidence": 0.81,
                "evidence_shot_ids": ["shot_12", "shot_19"],
                "coaching_action": "Cheek to the stock through the break; 10 bead-stare reps.",
            }
        ]
    )
    return {
        "schema_version": "1.0",
        "session_id": session_id,
        "athlete_pseudonym": "Athlete-7421",
        "headline": headline,
        "top_diagnostics": top,
        "notable_shots": [],
        "compared_to_history": {"sessions_compared": 0, "deltas": {}},
        "recommended_drills": ["drill_bead_stare"] if verifier_passed else [],
        "tone_mode": "coach" if verifier_passed else "silent",
        "language": "en-US",
        "confidence_overall": 0.74,
        "verifier_passed": verifier_passed,
        "model_version": "kimi-k2.6@1",
        "taxonomy_version": "taxonomy@2026-05-06",
        "generated_at": generated_at,
        "degraded": degraded,
    }


@pytest.mark.asyncio
async def test_post_then_get_coaching_note(client: AsyncClient) -> None:
    token, uid = await _signup_and_login(client, "cn1@example.com")
    sid = await _seed_session(uid)

    note = _note(sid)
    r = await client.post(
        f"/sessions/{sid}/coaching-note",
        headers={"Authorization": f"Bearer {token}"},
        json={"note": note},
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["session_id"] == sid
    assert out["headline"] == note["headline"]
    assert out["verifier_passed"] is True
    assert out["model_version"] == "kimi-k2.6@1"
    # The full structured note round-trips under `note`.
    assert out["note"]["top_diagnostics"][0]["category"] == "head_lift"
    assert out.get("id") and out.get("created_at")

    g = await client.get(
        f"/sessions/{sid}/coaching-note",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert g.status_code == 200
    assert g.json()["id"] == out["id"]


@pytest.mark.asyncio
async def test_get_returns_most_recent_after_regeneration(client: AsyncClient) -> None:
    token, uid = await _signup_and_login(client, "cn2@example.com")
    sid = await _seed_session(uid)

    first = _note(sid, headline="First pass — provisional read of the session, more to come.")
    second = _note(sid, headline="Updated note — regenerated after re-verification of the data.")
    for note in (first, second):
        r = await client.post(
            f"/sessions/{sid}/coaching-note",
            headers={"Authorization": f"Bearer {token}"},
            json={"note": note},
        )
        assert r.status_code == 201, r.text

    g = await client.get(
        f"/sessions/{sid}/coaching-note",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert g.status_code == 200
    assert g.json()["headline"] == second["headline"]


@pytest.mark.asyncio
async def test_get_404_when_no_note(client: AsyncClient) -> None:
    token, uid = await _signup_and_login(client, "cn3@example.com")
    sid = await _seed_session(uid)
    r = await client.get(
        f"/sessions/{sid}/coaching-note",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_degraded_note_persists(client: AsyncClient) -> None:
    """A degraded (verifier-failed, silent, no-diagnostics) note is a
    valid thing to store — the UI shows the honest 'analysis
    unavailable' state."""
    token, uid = await _signup_and_login(client, "cn4@example.com")
    sid = await _seed_session(uid)
    note = _note(
        sid,
        verifier_passed=False,
        degraded=True,
        headline="Session recorded; detailed analysis unavailable.",
    )
    r = await client.post(
        f"/sessions/{sid}/coaching-note",
        headers={"Authorization": f"Bearer {token}"},
        json={"note": note},
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["degraded"] is True
    assert out["verifier_passed"] is False
    assert out["tone_mode"] == "silent"


@pytest.mark.asyncio
async def test_post_422_on_missing_required_keys(client: AsyncClient) -> None:
    token, uid = await _signup_and_login(client, "cn5@example.com")
    sid = await _seed_session(uid)
    note = _note(sid)
    del note["model_version"]
    r = await client.post(
        f"/sessions/{sid}/coaching-note",
        headers={"Authorization": f"Bearer {token}"},
        json={"note": note},
    )
    assert r.status_code == 422
    assert "model_version" in r.text


@pytest.mark.asyncio
async def test_post_422_on_session_id_mismatch(client: AsyncClient) -> None:
    token, uid = await _signup_and_login(client, "cn6@example.com")
    sid = await _seed_session(uid)
    note = _note("some-other-session-id")
    r = await client.post(
        f"/sessions/{sid}/coaching-note",
        headers={"Authorization": f"Bearer {token}"},
        json={"note": note},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_post_404_cross_tenant(client: AsyncClient) -> None:
    _, ua = await _signup_and_login(client, "cnA@example.com")
    sid = await _seed_session(ua)
    token_b, _ = await _signup_and_login(client, "cnB@example.com")
    r = await client.post(
        f"/sessions/{sid}/coaching-note",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"note": _note(sid)},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_post_athlete_403(client: AsyncClient) -> None:
    _, uid = await _signup_and_login(client, "cn7@example.com")
    sid = await _seed_session(uid)
    ath_token, _ = issue_token(Principal(user_id=uid, tenant_id=f"solo:{uid}", role="athlete"))
    r = await client.post(
        f"/sessions/{sid}/coaching-note",
        headers={"Authorization": f"Bearer {ath_token}"},
        json={"note": _note(sid)},
    )
    assert r.status_code == 403
