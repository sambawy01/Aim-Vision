"""DTOs for auth, principal, and infrastructure endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class HealthOut(BaseModel):
    status: str = Field(default="ok")


class VersionOut(BaseModel):
    version: str
    git_sha: str
    env: str


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    display_name: str = Field(min_length=1, max_length=255)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class PrincipalOut(BaseModel):
    user_id: str
    tenant_id: str
    role: str
    display_name: str = ""


class MembershipOut(BaseModel):
    """One tenancy the user can operate in. Drives the web tenant switcher."""

    tenant_id: str
    display_name: str
    role: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    # The principal the token was minted for (the user's highest-privilege
    # membership) plus the full set of tenancies they can switch between.
    # The web client fills its auth + tenancy stores directly from these.
    principal: PrincipalOut
    memberships: list[MembershipOut]


class RefreshOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SwitchTenantIn(BaseModel):
    tenant_id: str


class SwitchTenantOut(BaseModel):
    """A re-minted access token bound to the newly-selected tenant, plus the
    principal under that tenant so the web can update its auth store."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    principal: PrincipalOut


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
