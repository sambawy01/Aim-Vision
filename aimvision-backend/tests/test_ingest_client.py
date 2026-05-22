"""IngestClient + make_ingest_client tests.

The backend post-session worker's HTTP client. Covered with
httpx.MockTransport (no live backend): the happy-path PATCH, the
non-2xx → IngestError mapping, and the config gate on
make_ingest_client.
"""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.services.ingest_client import IngestClient, IngestError
from app.workflows.activities.post_session import make_ingest_client


@pytest.mark.asyncio
async def test_patch_session_end_sends_partial_flag_and_returns_body() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = request.read()
        return httpx.Response(200, json={"id": "sess-1", "partial_session": True})

    async with IngestClient(
        "http://backend.test/",
        "tok-123",
        transport=httpx.MockTransport(handler),
    ) as client:
        out = await client.patch_session_end("sess-1", partial_session=True)

    assert seen["method"] == "PATCH"
    assert seen["path"] == "/sessions/sess-1/end"
    assert seen["auth"] == "Bearer tok-123"
    assert b'"partial_session":true' in bytes(seen["body"]).replace(b" ", b"")  # type: ignore[arg-type]
    assert out["id"] == "sess-1"


@pytest.mark.asyncio
async def test_patch_session_end_raises_on_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "session not found"})

    async with IngestClient(
        "http://backend.test",
        "tok",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(IngestError) as ei:
            await client.patch_session_end("missing", partial_session=False)

    assert ei.value.status_code == 404
    assert ei.value.detail == {"detail": "session not found"}


def test_make_ingest_client_returns_none_without_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.workflows.activities.post_session.get_settings",
        lambda: Settings(post_session_base_url=""),
    )
    assert make_ingest_client("solo:t-1") is None


def test_make_ingest_client_builds_client_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.workflows.activities.post_session.get_settings",
        lambda: Settings(post_session_base_url="http://backend.test"),
    )
    client = make_ingest_client("solo:t-1")
    assert isinstance(client, IngestClient)
