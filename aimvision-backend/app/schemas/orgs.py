"""Org listing DTOs.

The new-session form (web PR #69) currently requires a manual
org-id text input because the tenancy store carries `tenantId` but
not the user's org memberships. This module exposes the schema the
web client maps onto an org-picker dropdown.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OrgOut(BaseModel):
    """Org row scoped to the caller's tenant.

    `kind` mirrors `OrgKind` (`solo` / `club` / `federation`).
    `tenant_id` is included so the client can sanity-check the
    selection against the X-Tenant-Scope header it's about to use.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: str
    tenant_id: str
    federation_id: str | None
