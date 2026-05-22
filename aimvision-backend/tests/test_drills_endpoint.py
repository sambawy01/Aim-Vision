"""Drills catalog endpoint tests.

Covers GET /drills — the global coaching-drill catalog seeded at app
startup. The catalog is the source of truth the coaching-note
verifier validates `recommended_drills` against.
"""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient

from app.data.drills import DRILL_CATALOG
from app.services.auth import Principal, issue_token

_DRILL_ID_RE = re.compile(r"^drill_[a-z0-9_]{3,40}$")
_TAXONOMY = {
    "head_lift",
    "head_off_stock",
    "eye_dominance_failure",
    "low_mount_break",
    "foot_position",
    "body_alignment_off",
    "stopped_gun",
    "under_lead",
    "over_lead",
    "off_line",
    "short_follow_through",
    "dropped_gun_post_shot",
    "cause_unclear",
    "multi_factor",
    "in_session_pattern_flag",
}


async def _signup_and_login(client: AsyncClient, email: str) -> str:
    sr = await client.post(
        "/auth/signup",
        json={"email": email, "password": "p4ssw0rd!1234", "display_name": email.split("@")[0]},
    )
    assert sr.status_code == 201, sr.text
    uid = sr.json()["id"]
    token, _ = issue_token(Principal(user_id=uid, tenant_id=f"solo:{uid}", role="coach"))
    return token


@pytest.mark.asyncio
async def test_list_drills_returns_seeded_catalog(client: AsyncClient) -> None:
    token = await _signup_and_login(client, "drill1@example.com")
    r = await client.get("/drills", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    rows = r.json()
    # The full canonical catalog is seeded on startup.
    assert len(rows) == len(DRILL_CATALOG)
    ids = {d["id"] for d in rows}
    assert ids == {d["id"] for d in DRILL_CATALOG}


@pytest.mark.asyncio
async def test_drills_match_schema_id_pattern_and_taxonomy(client: AsyncClient) -> None:
    """Every drill id matches the coaching-note schema's drill pattern,
    and every target_category is a real taxonomy atom."""
    token = await _signup_and_login(client, "drill2@example.com")
    rows = (await client.get("/drills", headers={"Authorization": f"Bearer {token}"})).json()
    for d in rows:
        assert _DRILL_ID_RE.match(d["id"]), d["id"]
        assert d["name"] and d["description"]
        assert d["target_categories"], d["id"]
        for cat in d["target_categories"]:
            assert cat in _TAXONOMY, f"{d['id']} -> unknown category {cat}"


@pytest.mark.asyncio
async def test_catalog_covers_every_taxonomy_atom(client: AsyncClient) -> None:
    """Every diagnostic atom maps to at least one drill, so any
    diagnosis can recommend a real drill."""
    token = await _signup_and_login(client, "drill3@example.com")
    rows = (await client.get("/drills", headers={"Authorization": f"Bearer {token}"})).json()
    covered: set[str] = set()
    for d in rows:
        covered.update(d["target_categories"])
    assert covered >= _TAXONOMY, f"uncovered atoms: {_TAXONOMY - covered}"


@pytest.mark.asyncio
async def test_discipline_filter_includes_all_discipline_drills(client: AsyncClient) -> None:
    """A discipline filter returns that discipline's drills plus the
    universally-applicable ('all') ones."""
    token = await _signup_and_login(client, "drill4@example.com")
    skeet = (
        await client.get("/drills?discipline=skeet", headers={"Authorization": f"Bearer {token}"})
    ).json()
    # drill_pair_timing is skeet-specific; the rest are 'all'.
    disciplines = {d["discipline"] for d in skeet}
    assert disciplines <= {"skeet", "all"}
    assert any(d["id"] == "drill_pair_timing" for d in skeet)
    # trap: no trap-specific drill seeded, so only the 'all' ones (excludes skeet).
    trap = (
        await client.get("/drills?discipline=trap", headers={"Authorization": f"Bearer {token}"})
    ).json()
    assert all(d["discipline"] == "all" for d in trap)
    assert not any(d["id"] == "drill_pair_timing" for d in trap)


@pytest.mark.asyncio
async def test_drills_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/drills")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_seeding_is_idempotent_across_requests(client: AsyncClient) -> None:
    """Two lifespans / requests don't duplicate catalog rows (the
    client fixture re-runs lifespan; count stays stable)."""
    token = await _signup_and_login(client, "drill5@example.com")
    r1 = (await client.get("/drills", headers={"Authorization": f"Bearer {token}"})).json()
    r2 = (await client.get("/drills", headers={"Authorization": f"Bearer {token}"})).json()
    assert len(r1) == len(r2) == len(DRILL_CATALOG)
