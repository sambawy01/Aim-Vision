"""Principal resolution and scope-check helpers."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tenancy import Membership, Org
from .auth import Principal


async def assert_membership(session: AsyncSession, principal: Principal) -> None:
    """Verify the principal has at least one active membership matching tenant_id.

    For solo tenancies (`solo:<user_id>`) the user is implicitly a member of their own tenant.
    For org tenancies (`org:` / `fed:`) we look up an active membership row.
    """
    if principal.tenant_id.startswith("solo:"):
        if principal.tenant_id != f"solo:{principal.user_id}":
            raise PermissionError("solo tenant must match user_id")
        return

    stmt = (
        select(Membership)
        .join(Org, Org.id == Membership.org_id)
        .where(
            Membership.user_id == principal.user_id,
            Membership.is_active.is_(True),
            Org.tenant_id == principal.tenant_id,
        )
    )
    result = await session.execute(stmt)
    if result.scalars().first() is None:
        raise PermissionError(
            f"user {principal.user_id} has no active membership in {principal.tenant_id}"
        )


def parse_tenant_scope(scope: str) -> tuple[str, str]:
    """Parse `solo:<id>` / `org:<id>` / `fed:<id>` into (kind, id)."""
    if ":" not in scope:
        raise ValueError(f"malformed tenant scope: {scope!r}")
    kind, _, ref = scope.partition(":")
    if kind not in ("solo", "org", "fed"):
        raise ValueError(f"unknown tenant kind: {kind!r}")
    if not ref:
        raise ValueError("tenant scope missing id")
    return kind, ref
