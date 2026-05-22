"""Backend-side HTTP client for the post-session worker.

The ADR-0007 post-session worker is a separate deployable: it
orchestrates the pipeline on Temporal and persists results by calling
the backend API over HTTP (it does not share the API process's DB
session). This is the client those activities use.

It deliberately lives in the backend package — not imported from
`aimvision_ml.ingest.backend_client` — so the backend's Temporal
worker has no dependency on the heavy ML wheel (torch / onnxruntime).
The two clients share a wire contract, not code.

The surface is intentionally minimal: only `patch_session_end` today,
the one lifecycle step that needs no ML inference. The ML-bearing
steps (alignment, calibration, shot detection, diagnostics) run in
the ML worker via `aimvision_ml.ingest.run_post_session`, which owns
its own `BackendClient`.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx


class IngestError(RuntimeError):
    """Raised on a non-2xx backend response.

    Carries the status code so a Temporal retry policy can branch
    (retry 5xx/429, fail fast on 4xx)."""

    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(f"backend returned HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class IngestClient:
    """Async HTTP client for the post-session worker. Use as an async
    context manager so the connection pool is closed deterministically.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # `transport` lets tests inject httpx.MockTransport without a
        # live backend.
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_s,
            transport=transport,
        )

    async def __aenter__(self) -> IngestClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    @staticmethod
    def _raise_if_error(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        raise IngestError(resp.status_code, detail)

    async def patch_session_end(self, session_id: str, *, partial_session: bool) -> dict[str, Any]:
        """Close the session lifecycle (PATCH /sessions/{sid}/end).

        Idempotent on `ended_at` (preserved after the first call);
        `partial_session` is overwritten on every call so the worker
        can flip it on when its degraded-mode handler triggers.
        """
        resp = await self._client.patch(
            f"/sessions/{session_id}/end",
            json={"partial_session": partial_session},
        )
        self._raise_if_error(resp)
        return dict(resp.json())
