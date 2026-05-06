"""Smoke tests: /health, /version, /openapi.json."""

from __future__ import annotations

import json

from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_version_payload(client: AsyncClient) -> None:
    response = await client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"version", "git_sha", "env"}
    assert body["env"] == "test"


async def test_openapi_doc(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["openapi"].startswith("3.")
    assert "/health" in spec["paths"]
    assert "/auth/signup" in spec["paths"]
    # Round-trip valid JSON.
    json.dumps(spec)
