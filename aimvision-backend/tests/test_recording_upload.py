"""Recording upload integration tests — ADR-0009 slice 2.

Covers the `POST /sessions/{session_id}/recording` multipart ingest:
happy path, source_kind defaulting + override, cross-tenant isolation,
non-existent session, role gate, sha256 + size + file-on-disk assertions,
oversize rejection, and empty-body rejection.
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
from app.models import OrgKind, Recording, RecordingSourceKind, Session
from app.models.tenancy import Account, Org
from app.services.auth import Principal, issue_token
from app.services.storage import LocalFsStorage, set_storage


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path: Path):
    """Per-test tmp_path storage backend so files don't leak across tests."""
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
    """Insert a parent Session row directly via the ORM."""
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{user_id}"
    async with sm() as s, s.begin():
        s.add(Account(id=f"acc-{user_id}", name="acc", is_active=True))
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


def _fake_mp4_bytes(size: int = 2048) -> bytes:
    """Produce a deterministic byte string. NOT a valid MP4; the backend
    doesn't parse the container in slice 2 — it stores the bytes verbatim
    and sha256s them. A real MP4 fixture would need ffmpeg in CI."""
    return (b"\x00\x00\x00\x18ftypmp42" + b"AIM\x00" * 4)[:16] + b"x" * max(0, size - 16)


@pytest.mark.asyncio
async def test_upload_happy_path_writes_file_and_returns_metadata(
    client: AsyncClient, _isolated_storage: Path
) -> None:
    token, user_id = await _signup_and_login(client, "coach1@example.com")
    sid = await _seed_session(user_id)
    body = _fake_mp4_bytes(8192)
    expected_sha = hashlib.sha256(body).hexdigest()

    r = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("session.mp4", io.BytesIO(body), "video/mp4")},
        data={"source_kind": "phone_dev", "duration_ms": "1234"},
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["session_id"] == sid
    assert out["sha256"] == expected_sha
    assert out["duration_ms"] == 1234
    assert out["upload_state"] == "uploaded"
    assert out["source_kind"] == "phone_dev"
    assert out["storage_uri"].startswith(f"local://solo:{user_id}/{sid}/")

    # File actually on disk.
    files = list(_isolated_storage.rglob("*.mp4"))
    assert len(files) == 1
    assert files[0].read_bytes() == body


@pytest.mark.asyncio
async def test_upload_defaults_source_kind_to_hero13(
    client: AsyncClient, _isolated_storage: Path
) -> None:
    """Omitting `source_kind` should default to hero13 — keeps existing
    GoPro-path clients working without changes."""
    token, user_id = await _signup_and_login(client, "coach2@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("c.mp4", io.BytesIO(_fake_mp4_bytes()), "video/mp4")},
    )
    assert r.status_code == 201, r.text
    assert r.json()["source_kind"] == "hero13"


@pytest.mark.asyncio
async def test_upload_rejects_invalid_source_kind(
    client: AsyncClient, _isolated_storage: Path
) -> None:
    token, user_id = await _signup_and_login(client, "coach3@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("c.mp4", io.BytesIO(_fake_mp4_bytes()), "video/mp4")},
        data={"source_kind": "drone-totally-not-supported"},
    )
    # FastAPI returns 422 for enum mismatch.
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_upload_404_for_nonexistent_session(
    client: AsyncClient, _isolated_storage: Path
) -> None:
    token, _user_id = await _signup_and_login(client, "coach4@example.com")
    r = await client.post(
        "/sessions/sess-nope/recording",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("c.mp4", io.BytesIO(_fake_mp4_bytes()), "video/mp4")},
    )
    assert r.status_code == 404
    # File should NOT have been written — the existence check fires first.
    assert list(_isolated_storage.rglob("*.mp4")) == []


@pytest.mark.asyncio
async def test_upload_cross_tenant_404(client: AsyncClient, _isolated_storage: Path) -> None:
    """Tenant B cannot upload to a session owned by tenant A — the lookup
    is scoped on (id, tenant_id) so it 404s as if the row didn't exist."""
    _, user_a = await _signup_and_login(client, "tenantA@example.com")
    sid = await _seed_session(user_a)

    token_b, _ = await _signup_and_login(client, "tenantB@example.com")
    r = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token_b}"},
        files={"file": ("c.mp4", io.BytesIO(_fake_mp4_bytes()), "video/mp4")},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_upload_requires_coach_role(client: AsyncClient, _isolated_storage: Path) -> None:
    coach_token, user_id = await _signup_and_login(client, "coach5@example.com")
    sid = await _seed_session(user_id)

    # Mint an athlete-role token for the SAME user + tenant; the role gate
    # must fire before the row lookup.
    ath_token, _ = issue_token(
        Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role="athlete")
    )
    r = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {ath_token}"},
        files={"file": ("c.mp4", io.BytesIO(_fake_mp4_bytes()), "video/mp4")},
    )
    assert r.status_code == 403, r.text
    assert "coach" in r.json()["error"]
    # And the coach can still upload.
    r2 = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {coach_token}"},
        files={"file": ("c.mp4", io.BytesIO(_fake_mp4_bytes()), "video/mp4")},
    )
    assert r2.status_code == 201


@pytest.mark.asyncio
async def test_upload_rejects_empty_body(client: AsyncClient, _isolated_storage: Path) -> None:
    token, user_id = await _signup_and_login(client, "coach6@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("empty.mp4", io.BytesIO(b""), "video/mp4")},
    )
    assert r.status_code == 400, r.text
    assert "empty" in r.json()["error"].lower()


@pytest.mark.asyncio
async def test_upload_rejects_oversize(
    client: AsyncClient, _isolated_storage: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Capping max_recording_upload_bytes at 1 KiB and uploading 4 KiB
    should 413. The partial file should be cleaned up — no orphaned
    bytes-on-disk if we 413."""
    from app import config

    config.get_settings.cache_clear()
    settings = config.get_settings()
    monkeypatch.setattr(settings, "max_recording_upload_bytes", 1024)

    token, user_id = await _signup_and_login(client, "coach7@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("big.mp4", io.BytesIO(b"x" * 4096), "video/mp4")},
    )
    assert r.status_code == 413, r.text
    # The partial file got unlinked on the size-exceeded branch.
    leftover = list(_isolated_storage.rglob("*.mp4"))
    assert leftover == [], f"orphaned file(s): {leftover}"

    config.get_settings.cache_clear()


@pytest.mark.asyncio
async def test_db_row_carries_source_kind_for_aggregation_filtering(
    client: AsyncClient, _isolated_storage: Path
) -> None:
    """The DB row must persist `source_kind` so reports can filter phone_dev
    out of customer-facing rollups (ADR-0009 §17.3 hard line)."""
    token, user_id = await _signup_and_login(client, "coach8@example.com")
    sid = await _seed_session(user_id)
    body = _fake_mp4_bytes(1024)

    r = await client.post(
        f"/sessions/{sid}/recording",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("c.mp4", io.BytesIO(body), "video/mp4")},
        data={"source_kind": "phone_dev"},
    )
    assert r.status_code == 201

    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    async with sm() as s:
        from sqlalchemy import select

        row = (await s.execute(select(Recording))).scalars().first()
        assert row is not None
        assert row.source_kind == RecordingSourceKind.phone_dev
