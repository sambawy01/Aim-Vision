"""Sprint 4 EPIC 4.3 schema additions: CoachProfile, joint-controller ConsentRecord,
Recording.camera_clock_offset_ms, ShotEvent, federation_admin role.

Runs on the SQLite-backed test schema seeded by `db_schema` from conftest. The
real Postgres + RLS path is exercised separately in `test_tenancy_isolation.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import (
    Account,
    CoachProfile,
    ConsentRecord,
    OrgKind,
    Recording,
    Role,
    Session,
    Shot,
    ShotEvent,
    User,
)
from app.models.tenancy import Org


@pytest.mark.asyncio
async def test_role_enum_includes_federation_admin(db_schema: None) -> None:
    """Sprint 4 EPIC 4.3 adds the federation_admin role. The enum exposes it as
    an attribute and the StrEnum value round-trips."""
    assert Role.federation_admin.value == "federation_admin"
    assert "federation_admin" in {r.value for r in Role}


@pytest.mark.asyncio
async def test_coach_profile_round_trips(db_schema: None) -> None:
    """CoachProfile persists JSON certifications + specializations and enforces
    the (user_id, tenant_id) uniqueness so a coach in two tenants gets two
    distinct profile rows."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)

    async with sm() as s, s.begin():
        s.add_all(
            [
                Account(id="acct1", name="Acct 1"),
                User(
                    id="user1",
                    account_id="acct1",
                    email="coach@example.com",
                    password_hash="x",
                    display_name="Coach One",
                ),
            ]
        )
        s.add(
            CoachProfile(
                user_id="user1",
                tenant_id="org:fed1",
                bio="20-year national-team coach.",
                certifications=[{"issuer": "ISSF", "level": "national", "issued_at": "2018-06-01"}],
                specializations=["trap", "doubles_trap"],
                accepting_clients=True,
            )
        )
        s.add(
            CoachProfile(
                user_id="user1",
                tenant_id="org:club2",
                specializations=["skeet"],
                accepting_clients=False,
            )
        )

    async with sm() as s, s.begin():
        result = await s.execute(select(CoachProfile).where(CoachProfile.user_id == "user1"))
        rows = result.scalars().all()
        assert len(rows) == 2
        by_tenant = {r.tenant_id: r for r in rows}
        assert by_tenant["org:fed1"].specializations == ["trap", "doubles_trap"]
        assert by_tenant["org:fed1"].certifications[0]["issuer"] == "ISSF"
        assert by_tenant["org:club2"].accepting_clients is False


@pytest.mark.asyncio
async def test_consent_record_captures_joint_controllers(db_schema: None) -> None:
    """GDPR Art. 26: a consent that applies to a Federation + Club jointly must
    record both controller IDs and the agreement reference."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)

    async with sm() as s, s.begin():
        s.add(Account(id="acct1", name="Acct 1"))
        s.add(
            User(
                id="user1",
                account_id="acct1",
                email="athlete@example.com",
                password_hash="x",
                display_name="Athlete One",
            )
        )
        s.add(
            ConsentRecord(
                user_id="user1",
                tenant_id="org:fed1",
                purpose="video.coaching",
                purpose_version="v1",
                granted=True,
                granted_at=datetime(2026, 5, 13, tzinfo=UTC),
                processing_basis="consent",
                joint_controller_org_ids=["org:fed1", "org:club2"],
                joint_controller_agreement_ref="https://aimvision.io/jc/fed1-club2-v1.pdf",
            )
        )

    async with sm() as s, s.begin():
        result = await s.execute(select(ConsentRecord))
        row = result.scalar_one()
        assert row.processing_basis == "consent"
        assert row.joint_controller_org_ids == ["org:fed1", "org:club2"]
        assert row.joint_controller_agreement_ref.endswith(".pdf")
        # Forward-link to a Sprint-17 WithdrawalRequest stays nullable until then.
        assert row.withdrawal_request_id is None


@pytest.mark.asyncio
async def test_recording_persists_camera_clock_offset(db_schema: None) -> None:
    """`camera_clock_offset_ms` is the deterministic offset used to translate
    `Shot.device_clock_ns` into wall-clock time for multi-camera alignment.
    Sprint 4 EPIC 4.1 explicitly required this in the schema now."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)

    async with sm() as s, s.begin():
        s.add_all(
            [
                Account(id="acct1", name="Acct 1"),
                User(
                    id="user1",
                    account_id="acct1",
                    email="athlete@example.com",
                    password_hash="x",
                    display_name="A",
                ),
                Org(id="org1", kind=OrgKind.club, name="Club 1", tenant_id="org:club1"),
                Session(
                    id="sess1",
                    org_id="org1",
                    athlete_user_id="user1",
                    started_at=datetime(2026, 5, 13, tzinfo=UTC),
                    tenant_id="org:club1",
                ),
                Recording(
                    id="rec1",
                    session_id="sess1",
                    storage_uri="s3://aimvision/rec1.mp4",
                    camera_clock_offset_ms=-1234567,
                    tenant_id="org:club1",
                ),
            ]
        )

    async with sm() as s, s.begin():
        rec = (await s.execute(select(Recording).where(Recording.id == "rec1"))).scalar_one()
        assert rec.camera_clock_offset_ms == -1234567


@pytest.mark.asyncio
async def test_shot_events_are_append_only_ordered(db_schema: None) -> None:
    """ShotEvent is the append-only stream; `monotonic_seq` lets a consumer
    detect gaps without trusting wall-clock ordering. Verify ordered retrieval
    works for two namespaced event kinds on the same shot."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)

    async with sm() as s, s.begin():
        s.add_all(
            [
                Account(id="acct1", name="Acct 1"),
                User(
                    id="user1",
                    account_id="acct1",
                    email="a@example.com",
                    password_hash="x",
                    display_name="A",
                ),
                Org(id="org1", kind=OrgKind.club, name="C1", tenant_id="org:club1"),
                Session(
                    id="sess1",
                    org_id="org1",
                    athlete_user_id="user1",
                    started_at=datetime(2026, 5, 13, tzinfo=UTC),
                    tenant_id="org:club1",
                ),
                Shot(
                    id="shot1",
                    session_id="sess1",
                    monotonic_seq=1,
                    device_clock_ns=1_000_000_000,
                    server_clock_ns=1_000_000_500,
                    tenant_id="org:club1",
                ),
            ]
        )
        for kind, seq, payload in [
            ("audio.shot_detected", 1, {"snr_db": 28.4}),
            ("score.hit", 2, {"target_kind": "trap"}),
            ("diagnostic.head_tilt", 3, {"degrees": 4.2}),
        ]:
            s.add(
                ShotEvent(
                    shot_id="shot1",
                    event_kind=kind,
                    monotonic_seq=seq,
                    payload=payload,
                    produced_at=datetime(2026, 5, 13, tzinfo=UTC),
                    tenant_id="org:club1",
                )
            )

    async with sm() as s, s.begin():
        events = (
            (
                await s.execute(
                    select(ShotEvent)
                    .where(ShotEvent.shot_id == "shot1")
                    .order_by(ShotEvent.monotonic_seq)
                )
            )
            .scalars()
            .all()
        )
        assert [e.event_kind for e in events] == [
            "audio.shot_detected",
            "score.hit",
            "diagnostic.head_tilt",
        ]
        assert events[0].payload == {"snr_db": 28.4}
