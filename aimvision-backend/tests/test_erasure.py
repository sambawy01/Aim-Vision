"""Right-to-erasure endpoint + synthetic-athlete lifecycle tests.

Mirrors right-to-erasure-architecture.md §8: seed a subject with
sessions/shots/consent/coaching-note + tenant-encrypted data, submit
+ execute erasure, and assert the end-state — identifiers tombstoned,
references enumerated, and the tenant's data crypto-shredded.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind, Session
from app.models.coaching_note import CoachingNote
from app.models.consent import ConsentRecord
from app.models.session import Shot
from app.models.tenancy import Account, Org, User
from app.services import crypto_shred
from app.services.auth import Principal, issue_token
from app.services.crypto_shred import DekShreddedError


async def _signup_coach(client: AsyncClient, email: str) -> tuple[str, str]:
    sr = await client.post(
        "/auth/signup",
        json={"email": email, "password": "p4ssw0rd!1234", "display_name": email.split("@")[0]},
    )
    assert sr.status_code == 201, sr.text
    uid = sr.json()["id"]
    token, _ = issue_token(Principal(user_id=uid, tenant_id=f"solo:{uid}", role="coach"))
    return token, uid


async def _seed_subject_data(uid: str) -> None:
    """Seed a session + shot + consent + coaching note for the subject."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{uid}"
    sid = f"sess-{uid}"
    async with sm() as s, s.begin():
        s.add(Account(id=f"acc-{uid}", name="acc", is_active=True))
        s.add(Org(id=f"org-{uid}", kind=OrgKind.solo, name="solo", tenant_id=tenant))
        s.add(
            Session(
                id=sid,
                org_id=f"org-{uid}",
                athlete_user_id=uid,
                started_at=datetime.now(UTC),
                tenant_id=tenant,
            )
        )
        s.add(
            Shot(
                id=f"{sid}-shot-0",
                tenant_id=tenant,
                session_id=sid,
                monotonic_seq=0,
                device_clock_ns=0,
                server_clock_ns=0,
                shot_kind="single",
            )
        )
        s.add(
            ConsentRecord(
                id=f"consent-{uid}",
                tenant_id=tenant,
                user_id=uid,
                purpose="ml_training",
                purpose_version="1.0",
                granted=True,
                granted_at=datetime.now(UTC),
            )
        )
        s.add(
            CoachingNote(
                id=f"note-{uid}",
                tenant_id=tenant,
                session_id=sid,
                headline="A session note that will be shredded.",
                tone_mode="coach",
                language="en-US",
                verifier_passed=True,
                degraded=False,
                confidence_overall=0.5,
                model_version="kimi-k2.6@1",
                taxonomy_version="taxonomy@2026-05-06",
                generated_at=datetime.now(UTC),
                note_json={"headline": "x"},
            )
        )
        # Encrypt a tenant blob so we can prove the shred takes effect.
        await crypto_shred.encrypt_for_tenant(s, tenant, b"raw-pose-keypoints")


@pytest.mark.asyncio
async def test_erasure_lifecycle_tombstones_and_crypto_shreds(client: AsyncClient) -> None:
    token, uid = await _signup_coach(client, "erase1@example.com")
    await _seed_subject_data(uid)
    tenant = f"solo:{uid}"

    # Submit.
    r = await client.post(
        "/erasure",
        headers={"Authorization": f"Bearer {token}"},
        json={"athlete_user_id": uid, "reason": "subject DSAR request"},
    )
    assert r.status_code == 201, r.text
    ticket = r.json()
    assert ticket["status"] == "pending"
    assert ticket["requested_by"] == uid
    ticket_id = ticket["id"]

    # Execute.
    e = await client.post(
        f"/erasure/{ticket_id}/execute",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert e.status_code == 200, e.text
    done = e.json()
    assert done["status"] == "completed"
    assert done["completed_at"] is not None
    assert done["references"] == {
        "sessions": 1,
        "shots": 1,
        "coaching_notes": 1,
        "consent_records": 1,
    }

    # Subject identifiers tombstoned in the operational DB.
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s:
        user = await s.get(User, uid)
        assert user is not None
        assert user.email == f"erased+{uid}@erased.invalid"
        assert user.display_name == "erased"
        assert user.is_active is False

        # The tenant DEK is shredded: encrypting/decrypting now fails.
        with pytest.raises(DekShreddedError):
            await crypto_shred.encrypt_for_tenant(s, tenant, b"anything")


@pytest.mark.asyncio
async def test_execute_is_idempotent(client: AsyncClient) -> None:
    token, uid = await _signup_coach(client, "erase2@example.com")
    await _seed_subject_data(uid)
    r = await client.post(
        "/erasure",
        headers={"Authorization": f"Bearer {token}"},
        json={"athlete_user_id": uid, "reason": "x"},
    )
    ticket_id = r.json()["id"]
    first = await client.post(
        f"/erasure/{ticket_id}/execute", headers={"Authorization": f"Bearer {token}"}
    )
    second = await client.post(
        f"/erasure/{ticket_id}/execute", headers={"Authorization": f"Bearer {token}"}
    )
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["completed_at"] == first.json()["completed_at"]


@pytest.mark.asyncio
async def test_execute_cross_tenant_404(client: AsyncClient) -> None:
    token_a, ua = await _signup_coach(client, "eraseA@example.com")
    await _seed_subject_data(ua)
    r = await client.post(
        "/erasure",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"athlete_user_id": ua, "reason": "x"},
    )
    ticket_id = r.json()["id"]

    token_b, _ = await _signup_coach(client, "eraseB@example.com")
    e = await client.post(
        f"/erasure/{ticket_id}/execute", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert e.status_code == 404


@pytest.mark.asyncio
async def test_submit_requires_coach_role(client: AsyncClient) -> None:
    _, uid = await _signup_coach(client, "erase3@example.com")
    ath_token, _ = issue_token(Principal(user_id=uid, tenant_id=f"solo:{uid}", role="athlete"))
    r = await client.post(
        "/erasure",
        headers={"Authorization": f"Bearer {ath_token}"},
        json={"athlete_user_id": uid, "reason": "x"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_ticket(client: AsyncClient) -> None:
    token, uid = await _signup_coach(client, "erase4@example.com")
    r = await client.post(
        "/erasure",
        headers={"Authorization": f"Bearer {token}"},
        json={"athlete_user_id": uid, "reason": "x"},
    )
    ticket_id = r.json()["id"]
    g = await client.get(f"/erasure/{ticket_id}", headers={"Authorization": f"Bearer {token}"})
    assert g.status_code == 200
    assert g.json()["id"] == ticket_id
    assert g.json()["status"] == "pending"
