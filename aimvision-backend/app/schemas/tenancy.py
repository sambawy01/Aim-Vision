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


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str


class PrincipalOut(BaseModel):
    user_id: str
    tenant_id: str
    role: str
