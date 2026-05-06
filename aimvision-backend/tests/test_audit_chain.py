"""Audit hash-chain integrity tests."""

from __future__ import annotations

from app.db import system_session
from app.services.audit import AuditEventInput, AuditEventWriter


async def _emit(writer: AuditEventWriter, tenant: str, n: int) -> None:
    for i in range(n):
        await writer.append(
            AuditEventInput(
                event_type="test.event",
                actor_principal=f"user:{tenant}",
                tenant_id=tenant,
                action="create",
                target_resource="thing",
                target_id=f"id-{i}",
                extra={"i": i},
            )
        )


async def test_chain_integrity_two_tenants(db_schema: None) -> None:
    async with system_session() as session:
        writer = AuditEventWriter(session)
        await _emit(writer, "org:tenant_a", 5)
        await _emit(writer, "org:tenant_b", 3)

    async with system_session() as session:
        writer = AuditEventWriter(session)
        assert await writer.verify_chain("org:tenant_a") is True
        assert await writer.verify_chain("org:tenant_b") is True


async def test_chain_detects_tampering(db_schema: None) -> None:
    async with system_session() as session:
        writer = AuditEventWriter(session)
        await _emit(writer, "org:tenant_x", 4)

    # Tamper with one row's `action` -- the recomputed hash will not match.
    from sqlalchemy import select, update

    from app.models.audit import AuditEvent

    async with system_session() as session:
        result = await session.execute(
            select(AuditEvent.event_id)
            .where(AuditEvent.tenant_id == "org:tenant_x")
            .order_by(AuditEvent.timestamp_ns.asc())
        )
        ids = [row[0] for row in result.all()]
        # Tamper the second event so chain breaks at index 1 onward.
        await session.execute(
            update(AuditEvent).where(AuditEvent.event_id == ids[1]).values(action="tampered")
        )

    async with system_session() as session:
        writer = AuditEventWriter(session)
        assert await writer.verify_chain("org:tenant_x") is False
