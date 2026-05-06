"""Append-only, hash-chained audit event writer (per audit-logging-spec.md §3-§4).

The chain is keyed by `tenant_id`. Each event's `event_hash` is
``BLAKE2b(prev_event_hash || canonical_json(event-without-hash))``. Verification
recomputes hashes in `timestamp_ns` order per tenant.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditEvent

GENESIS_HASH = "blake2b:" + ("0" * 128)


@dataclass
class AuditEventInput:
    event_type: str
    actor_principal: str
    tenant_id: str
    action: str
    result: str = "success"
    actor_role: str | None = None
    target_resource: str | None = None
    target_id: str | None = None
    request_id: str | None = None
    ip_addr_hash: str | None = None
    user_agent_hash: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _hash(prev: str, payload: dict[str, Any]) -> str:
    digest = hashlib.blake2b(prev.encode("utf-8") + _canonical_json(payload)).hexdigest()
    return f"blake2b:{digest}"


def _event_id() -> str:
    # uuid7-shaped: ms timestamp prefix + uuid4 randomness.
    ts_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = uuid.uuid4().int & ((1 << 80) - 1)
    val = (ts_ms << 80) | rand
    hex32 = f"{val:032x}"
    return f"{hex32[0:8]}-{hex32[8:12]}-7{hex32[13:16]}-{hex32[16:20]}-{hex32[20:32]}"


class AuditEventWriter:
    """Persists audit events with per-tenant hash chains.

    Single-process correctness only -- production must add
    ``pg_advisory_xact_lock(hash(tenant_id))`` (see audit-logging-spec.md §4.2).
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _last_hash_for(self, tenant_id: str) -> str:
        stmt = (
            select(AuditEvent.event_hash)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.timestamp_ns.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        prev: str | None = result.scalars().first()
        return prev or GENESIS_HASH

    async def append(self, event: AuditEventInput) -> AuditEvent:
        prev_hash = await self._last_hash_for(event.tenant_id)
        timestamp_ns = time.time_ns()
        event_id = _event_id()
        payload: dict[str, Any] = {
            "event_id": event_id,
            "event_type": event.event_type,
            "actor_principal": event.actor_principal,
            "actor_role": event.actor_role,
            "tenant_id": event.tenant_id,
            "target_resource": event.target_resource,
            "target_id": event.target_id,
            "action": event.action,
            "result": event.result,
            "request_id": event.request_id,
            "ip_addr_hash": event.ip_addr_hash,
            "user_agent_hash": event.user_agent_hash,
            "extra": event.extra,
            "timestamp_ns": timestamp_ns,
        }
        event_hash = _hash(prev_hash, payload)
        row = AuditEvent(
            **payload,
            prev_event_hash=prev_hash,
            event_hash=event_hash,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def verify_chain(self, tenant_id: str) -> bool:
        """Walk the chain for a tenant, asserting prev/hash continuity."""
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.timestamp_ns.asc())
        )
        result = await self.session.execute(stmt)
        events: list[AuditEvent] = list(result.scalars().all())
        prev = GENESIS_HASH
        for ev in events:
            if ev.prev_event_hash != prev:
                return False
            payload = {
                "event_id": ev.event_id,
                "event_type": ev.event_type,
                "actor_principal": ev.actor_principal,
                "actor_role": ev.actor_role,
                "tenant_id": ev.tenant_id,
                "target_resource": ev.target_resource,
                "target_id": ev.target_id,
                "action": ev.action,
                "result": ev.result,
                "request_id": ev.request_id,
                "ip_addr_hash": ev.ip_addr_hash,
                "user_agent_hash": ev.user_agent_hash,
                "extra": ev.extra or {},
                "timestamp_ns": ev.timestamp_ns,
            }
            recomputed = _hash(prev, payload)
            if recomputed != ev.event_hash:
                return False
            prev = ev.event_hash
        return True


__all__ = [
    "GENESIS_HASH",
    "AuditEventInput",
    "AuditEventWriter",
    "asdict",  # convenience re-export for callers building events from dataclasses
]
