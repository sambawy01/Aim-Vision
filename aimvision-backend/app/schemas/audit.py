"""Audit event DTO (read-only API view)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    event_type: str
    actor_principal: str
    actor_role: str | None
    tenant_id: str
    target_resource: str | None
    target_id: str | None
    action: str
    result: str
    request_id: str | None
    extra: dict[str, Any]
    timestamp_ns: int
    prev_event_hash: str
    event_hash: str
