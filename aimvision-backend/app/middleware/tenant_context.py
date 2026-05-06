"""Tenant-context middleware.

Resolves the principal from `Authorization: Bearer <jwt>` + `X-Tenant-Scope`
header (per multi-tenant-isolation.md §1.1) and stashes it on `request.state`
for downstream dependencies. The actual ``SET LOCAL app.current_principal``
happens in ``db.tenant_session`` when a session is opened, so transaction-pool
mode is safe.
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from ..services.auth import Principal, verify_token


class TenantContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.principal = self._resolve_principal(request)

        response: Response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    @staticmethod
    def _resolve_principal(request: Request) -> Principal | None:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        token = auth.split(None, 1)[1].strip()
        try:
            principal = verify_token(token)
        except Exception:
            return None

        scope_header = request.headers.get("x-tenant-scope")
        if scope_header and scope_header != principal.tenant_id:
            # Token-bound tenant wins; explicit scope-switch endpoint will rotate the token.
            return None
        return principal
