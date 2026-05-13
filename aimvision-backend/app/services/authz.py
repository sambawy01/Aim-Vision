"""Role-based authorization helpers — Sprint 4 EPIC 4.3.

The Role enum (models/tenancy.py) is the source of truth for the names;
this module layers the *hierarchy* and the FastAPI dependency factories
that gate endpoints.

Hierarchy (each role is a superset of the ones below it for app-level
gates; tenancy scoping is enforced separately by RLS + the tenant_id
column):

  system_admin       internal, not membership-backed
  federation_admin   cross-club within a Federation Org
  admin              single Org admin (club/federation)
  coach              session capture + annotations within their cohorts
  athlete            own data
  parent             linked-minor data (handled by ConsentRecord)

A `federation_admin` resolves as `admin` for permission checks against
clubs subordinate to their Federation Org. We do NOT collapse the two
roles in the database; the hierarchy lives here so the principal table
stays a clean enum.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable

from fastapi import Depends, HTTPException, status

from ..deps import current_principal
from ..models.tenancy import Role
from .auth import Principal

ROLE_RANK: dict[str, int] = {
    Role.parent.value: 1,
    Role.athlete.value: 2,
    Role.coach.value: 3,
    Role.admin.value: 4,
    Role.federation_admin.value: 5,
    # system_admin is not in the Role enum (it's an out-of-band internal
    # claim, never persisted to memberships); we still recognize it here
    # so an ops principal minted by the bootstrap pipeline can reach
    # everything.
    "system_admin": 99,
}


def has_role(principal_role: str, *required_any_of: str) -> bool:
    """True if `principal_role`'s rank meets or exceeds the minimum rank
    among `required_any_of`. Unknown roles always fail closed."""
    if not required_any_of:
        raise ValueError("must pass at least one required role")
    needed = min(ROLE_RANK.get(r, 999_999) for r in required_any_of)
    return ROLE_RANK.get(principal_role, -1) >= needed


def require_role(*required_any_of: str) -> Callable[[Principal], Awaitable[Principal]]:
    """Build a FastAPI dependency that 403s if the principal lacks any of
    the required roles. Usage:

        @router.get("/admin-only", dependencies=[Depends(require_role("admin"))])
        async def admin_only(): ...

    Or, when the handler also needs the Principal:

        @router.get("/x")
        async def x(p: Principal = Depends(require_role("federation_admin"))):
            ...
    """
    if not required_any_of:
        raise ValueError("must pass at least one required role")

    async def _dep(principal: Principal = Depends(current_principal)) -> Principal:
        if not has_role(principal.role, *required_any_of):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(f"requires one of: {', '.join(required_any_of)}; have: {principal.role}"),
            )
        return principal

    return _dep


def assert_can_act_as(principal: Principal, on_tenant_id: str) -> None:
    """Cross-tenant authorization check.

    Most endpoints rely on RLS to make cross-tenant rows invisible. But
    some flows (federation admin viewing a club's data) require a
    *deliberate* cross-tenant action and need the app layer to assert
    that the principal's role + tenant hierarchy permits it.

    Today the rule is simple: same tenant_id, or principal is
    system_admin. Federation→club cross-tenant access lands in the next
    slice once Org.federation_id traversal is wired into the session
    factory.
    """
    if principal.tenant_id == on_tenant_id:
        return
    if principal.role == "system_admin":
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="principal cannot act on a different tenant",
    )


def all_roles_lower_than(role: str) -> Iterable[str]:
    """Return the role values strictly below `role` in the hierarchy.
    Used by admin endpoints that should be able to manage subordinate
    roles but not peers or superiors."""
    if role not in ROLE_RANK:
        return ()
    threshold = ROLE_RANK[role]
    return tuple(r for r, rank in ROLE_RANK.items() if rank < threshold)
