"""Sprint 6 EPIC 6.5 active learning queue API tests.

Solo-tenant signup gives each test a fresh principal; the queue table
inherits tenant_id from that principal at insert time. End-to-end flow:
enqueue -> list -> claim -> label, plus the rejection paths.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind, Session
from app.models.tenancy import Org
from app.services.auth import Principal, issue_token


async def _signup_and_login(
    client: AsyncClient, email: str, *, role: str = "coach"
) -> tuple[str, str]:
    """Returns (bearer_token, user_id). The token is minted with
    `role=coach` by default so the annotator endpoints (gated on
    require_role("coach")) accept it. Pass `role="athlete"` to exercise
    the 403 path.

    Solo tenant remains implicit on signup (`solo:<user_id>`)."""
    sr = await client.post(
        "/auth/signup",
        json={"email": email, "password": "p4ssw0rd!1234", "display_name": email.split("@")[0]},
    )
    assert sr.status_code == 201, sr.text
    user_id = sr.json()["id"]
    token, _ = issue_token(Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role=role))
    return token, user_id


async def _seed_session(user_id: str) -> str:
    """Insert a Session row directly via the ORM. The active-learning
    endpoints require a session_id FK to be valid."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s, s.begin():
        tenant = f"solo:{user_id}"
        s.add(Org(id=f"org-{user_id}", kind=OrgKind.solo, name="solo", tenant_id=tenant))
        s.add(
            Session(
                id=f"sess-{user_id}",
                org_id=f"org-{user_id}",
                athlete_user_id=user_id,
                started_at=datetime.now(UTC),
                tenant_id=tenant,
            )
        )
    return f"sess-{user_id}"


@pytest.mark.asyncio
async def test_enqueue_and_list_in_priority_order(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "annot1@example.com")
    sid = await _seed_session(user_id)
    h = {"Authorization": f"Bearer {token}"}

    for priority, conf in [(0, 0.42), (10, 0.31), (5, 0.55)]:
        r = await client.post(
            "/active-learning/items",
            headers=h,
            json={
                "session_id": sid,
                "model_name": "audio_shot_detector",
                "model_version": "v0.1.0",
                "prediction": {"shots": []},
                "confidence": conf,
                "uncertainty_signal": "low_confidence",
                "priority": priority,
            },
        )
        assert r.status_code == 201, r.text

    r = await client.get("/active-learning/items?status=pending", headers=h)
    assert r.status_code == 200
    items = r.json()
    assert [i["priority"] for i in items] == [10, 5, 0]


@pytest.mark.asyncio
async def test_claim_then_label_full_cycle(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "annot2@example.com")
    sid = await _seed_session(user_id)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/active-learning/items",
        headers=h,
        json={
            "session_id": sid,
            "model_name": "diagnostic",
            "model_version": "v0.1.0",
            "prediction": {"label": "head_tilt", "p": 0.55},
            "confidence": 0.55,
            "uncertainty_signal": "low_confidence",
        },
    )
    item_id = r.json()["id"]

    claim = await client.post(f"/active-learning/items/{item_id}/claim", headers=h)
    assert claim.status_code == 200
    body = claim.json()
    assert body["status"] == "claimed"
    assert body["annotator_user_id"] == user_id
    assert body["claimed_at"] is not None

    lbl = await client.post(
        f"/active-learning/items/{item_id}/label",
        headers=h,
        json={"labels": {"diagnostic": "head_tilt_high", "severity": 2}, "annotator_note": "clear"},
    )
    assert lbl.status_code == 200
    body = lbl.json()
    assert body["status"] == "labelled"
    assert body["labels"] == {"diagnostic": "head_tilt_high", "severity": 2}
    assert body["labelled_at"] is not None


@pytest.mark.asyncio
async def test_double_claim_returns_409(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "annot3@example.com")
    sid = await _seed_session(user_id)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/active-learning/items",
        headers=h,
        json={
            "session_id": sid,
            "model_name": "audio_shot_detector",
            "model_version": "v0.1.0",
            "prediction": {"shots": []},
            "confidence": 0.42,
            "uncertainty_signal": "low_confidence",
        },
    )
    item_id = r.json()["id"]

    first = await client.post(f"/active-learning/items/{item_id}/claim", headers=h)
    assert first.status_code == 200
    second = await client.post(f"/active-learning/items/{item_id}/claim", headers=h)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_only_claimer_can_label(client: AsyncClient) -> None:
    token_a, user_a = await _signup_and_login(client, "annotA@example.com")
    sid = await _seed_session(user_a)
    h_a = {"Authorization": f"Bearer {token_a}"}

    # Enqueue in tenant A.
    r = await client.post(
        "/active-learning/items",
        headers=h_a,
        json={
            "session_id": sid,
            "model_name": "pose",
            "model_version": "v0.1.0",
            "prediction": {"keypoints": []},
            "confidence": 0.4,
            "uncertainty_signal": "low_confidence",
        },
    )
    item_id = r.json()["id"]

    # User A claims it.
    await client.post(f"/active-learning/items/{item_id}/claim", headers=h_a)

    # A different user (different solo tenant) cannot even see it, but
    # let's also verify the same-tenant-different-user case: we manually
    # mint a second user inside tenant A's session_id space. Solo tenants
    # are 1:1 with users by design, so this is documented behavior — the
    # only way to have two users in one tenant is via Memberships
    # (federation/club). For the unit-test path, attempting to label
    # someone-else's-claimed-item from another tenant is a 404 (RLS), and
    # the 403 path is exercised by a federation-tier integration test
    # which lives elsewhere once we wire it up. So here we just confirm
    # the 404 case to catch the cross-tenant leak regression.
    token_b, _ = await _signup_and_login(client, "annotB@example.com")
    h_b = {"Authorization": f"Bearer {token_b}"}
    lbl = await client.post(
        f"/active-learning/items/{item_id}/label",
        headers=h_b,
        json={"labels": {"x": 1}},
    )
    assert lbl.status_code == 404


@pytest.mark.asyncio
async def test_label_before_claim_returns_409(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "annot4@example.com")
    sid = await _seed_session(user_id)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/active-learning/items",
        headers=h,
        json={
            "session_id": sid,
            "model_name": "diagnostic",
            "model_version": "v0.1.0",
            "prediction": {},
            "confidence": 0.4,
            "uncertainty_signal": "low_confidence",
        },
    )
    item_id = r.json()["id"]

    lbl = await client.post(
        f"/active-learning/items/{item_id}/label", headers=h, json={"labels": {}}
    )
    assert lbl.status_code == 409


@pytest.mark.asyncio
async def test_discard_cannot_undo_labelled_item(client: AsyncClient) -> None:
    token, user_id = await _signup_and_login(client, "annot5@example.com")
    sid = await _seed_session(user_id)
    h = {"Authorization": f"Bearer {token}"}

    r = await client.post(
        "/active-learning/items",
        headers=h,
        json={
            "session_id": sid,
            "model_name": "diagnostic",
            "model_version": "v0.1.0",
            "prediction": {},
            "confidence": 0.4,
            "uncertainty_signal": "low_confidence",
        },
    )
    item_id = r.json()["id"]

    await client.post(f"/active-learning/items/{item_id}/claim", headers=h)
    await client.post(
        f"/active-learning/items/{item_id}/label", headers=h, json={"labels": {"x": 1}}
    )

    disc = await client.post(f"/active-learning/items/{item_id}/discard", headers=h)
    assert disc.status_code == 409
    assert "training set" in disc.json()["error"]


@pytest.mark.asyncio
async def test_claim_requires_coach_role(client: AsyncClient) -> None:
    """Athletes cannot claim items — the require_role("coach") gate 403s
    them before they reach the row, even on their own tenant."""
    coach_token, user_id = await _signup_and_login(client, "coach1@example.com")
    sid = await _seed_session(user_id)
    h_coach = {"Authorization": f"Bearer {coach_token}"}

    r = await client.post(
        "/active-learning/items",
        headers=h_coach,
        json={
            "session_id": sid,
            "model_name": "x",
            "model_version": "v",
            "prediction": {},
            "confidence": 0.1,
            "uncertainty_signal": "low_confidence",
        },
    )
    item_id = r.json()["id"]

    # Mint an athlete token for the SAME user + tenant. The role gate
    # must fire before the tenant check so we know the gate works in
    # isolation.
    ath_token, _ = (
        issue_token(Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role="athlete"))[0],
        user_id,
    )
    h_ath = {"Authorization": f"Bearer {ath_token}"}
    claim = await client.post(f"/active-learning/items/{item_id}/claim", headers=h_ath)
    assert claim.status_code == 403, claim.text
    assert "coach" in claim.json()["error"]


@pytest.mark.asyncio
async def test_cross_tenant_items_invisible(client: AsyncClient) -> None:
    token_a, user_a = await _signup_and_login(client, "tenantA@example.com")
    sid_a = await _seed_session(user_a)
    h_a = {"Authorization": f"Bearer {token_a}"}

    await client.post(
        "/active-learning/items",
        headers=h_a,
        json={
            "session_id": sid_a,
            "model_name": "x",
            "model_version": "v",
            "prediction": {},
            "confidence": 0.1,
            "uncertainty_signal": "low_confidence",
        },
    )

    token_b, _ = await _signup_and_login(client, "tenantB@example.com")
    h_b = {"Authorization": f"Bearer {token_b}"}

    listing = await client.get("/active-learning/items?status=pending", headers=h_b)
    assert listing.status_code == 200
    # Tenant B sees zero items; SQLite path enforces the explicit
    # tenant_id filter in the router. The Postgres path additionally
    # enforces RLS at the row level (exercised in test_tenancy_isolation).
    assert listing.json() == []
