"""Sprint 4 EPIC 4.3: role-based authorization unit tests.

Tests target services/authz.py directly. The FastAPI dep-injection path
is exercised by the active-learning and other existing route tests once
those handlers add `dependencies=[Depends(require_role(...))]`.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.auth import Principal
from app.services.authz import (
    all_roles_lower_than,
    assert_can_act_as,
    has_role,
    require_role,
)


def _principal(role: str, tenant_id: str = "org:club1") -> Principal:
    return Principal(user_id="user1", tenant_id=tenant_id, role=role)


def test_has_role_athlete_cannot_pass_admin_gate() -> None:
    assert has_role("athlete", "admin") is False


def test_has_role_admin_passes_athlete_gate() -> None:
    assert has_role("admin", "athlete") is True


def test_has_role_federation_admin_passes_admin_gate() -> None:
    """Per §EPIC 4.3 federation_admin is a superset of admin."""
    assert has_role("federation_admin", "admin") is True


def test_has_role_admin_does_not_pass_federation_admin_gate() -> None:
    """The reverse must NOT hold — a club admin cannot escalate."""
    assert has_role("admin", "federation_admin") is False


def test_has_role_any_of_multiple_uses_lowest_rank() -> None:
    """`require_role('coach', 'admin')` means 'coach OR higher'."""
    assert has_role("coach", "coach", "admin") is True
    assert has_role("athlete", "coach", "admin") is False


def test_has_role_unknown_role_fails_closed() -> None:
    assert has_role("unknown_made_up_role", "athlete") is False


def test_has_role_empty_required_raises() -> None:
    with pytest.raises(ValueError):
        has_role("admin")


def test_system_admin_passes_everything() -> None:
    """The out-of-band system_admin claim is the escape hatch for the
    bootstrap pipeline and ops endpoints."""
    assert has_role("system_admin", "federation_admin") is True
    assert has_role("system_admin", "admin") is True


@pytest.mark.asyncio
async def test_require_role_dep_returns_principal_when_allowed() -> None:
    dep = require_role("athlete")
    p = _principal("admin")
    out = await dep(principal=p)
    assert out is p


@pytest.mark.asyncio
async def test_require_role_dep_403s_when_denied() -> None:
    dep = require_role("admin")
    p = _principal("athlete")
    with pytest.raises(HTTPException) as ei:
        await dep(principal=p)
    assert ei.value.status_code == 403
    assert "admin" in ei.value.detail
    assert "athlete" in ei.value.detail


def test_require_role_factory_validates_args() -> None:
    with pytest.raises(ValueError):
        require_role()


def test_assert_can_act_as_same_tenant_passes() -> None:
    p = _principal("admin", tenant_id="org:club1")
    assert_can_act_as(p, "org:club1")  # does not raise


def test_assert_can_act_as_cross_tenant_403s_for_admin() -> None:
    p = _principal("admin", tenant_id="org:club1")
    with pytest.raises(HTTPException) as ei:
        assert_can_act_as(p, "org:club2")
    assert ei.value.status_code == 403


def test_assert_can_act_as_system_admin_can_cross_tenant() -> None:
    p = _principal("system_admin", tenant_id="ops:internal")
    assert_can_act_as(p, "org:club2")  # does not raise


def test_all_roles_lower_than_returns_strict_subset() -> None:
    lower = set(all_roles_lower_than("admin"))
    assert "coach" in lower
    assert "athlete" in lower
    assert "parent" in lower
    assert "admin" not in lower
    assert "federation_admin" not in lower
