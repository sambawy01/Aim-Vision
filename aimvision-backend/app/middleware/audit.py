"""Audit-emission middleware: every authenticated request produces an audit event.

Best-effort: failures here must not bring down the request, but on the production
audit DB outage path the policy is fail-closed for write-side actions
(audit-logging-spec.md §9). That escalation lives in the writer, not here.
"""

from __future__ import annotations

import hashlib
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from ..config import get_settings
from ..db import system_session
from ..services.audit import AuditEventInput, AuditEventWriter
from ..services.auth import Principal

logger = logging.getLogger("aimvision.audit")


def _hash_with_salt(value: str | None, salt: str) -> str | None:
    if not value:
        return None
    return "blake2b:" + hashlib.blake2b(f"{salt}|{value}".encode()).hexdigest()


class AuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, exclude_paths: tuple[str, ...] = ()) -> None:
        super().__init__(app)
        self.exclude_paths = exclude_paths

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        response: Response = await call_next(request)
        if request.url.path in self.exclude_paths:
            return response

        principal: Principal | None = getattr(request.state, "principal", None)
        if principal is None:
            return response

        try:
            settings = get_settings()
            ip = request.client.host if request.client else None
            ua = request.headers.get("user-agent")
            event = AuditEventInput(
                event_type="api.request",
                actor_principal=f"user:{principal.user_id}",
                actor_role=principal.role,
                tenant_id=principal.tenant_id,
                action=request.method.lower(),
                result="success" if response.status_code < 400 else "failure",
                target_resource="endpoint",
                target_id=request.url.path,
                request_id=getattr(request.state, "request_id", None),
                ip_addr_hash=_hash_with_salt(ip, settings.ip_hash_salt),
                user_agent_hash=_hash_with_salt(ua, settings.ip_hash_salt),
                extra={"status": response.status_code},
            )
            async with system_session() as session:
                await AuditEventWriter(session).append(event)
        except Exception as exc:
            logger.warning("audit emission failed: %s", exc)
        return response
