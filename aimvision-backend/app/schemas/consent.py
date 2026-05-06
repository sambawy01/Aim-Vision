"""Consent DTOs (GDPR Art. 9 separable per purpose)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConsentGrantIn(BaseModel):
    purpose: str = Field(min_length=1, max_length=128)
    purpose_version: str = Field(min_length=1, max_length=32)
    proof_uri: str | None = Field(default=None, max_length=1024)


class ConsentRevokeIn(BaseModel):
    purpose: str = Field(min_length=1, max_length=128)
    purpose_version: str = Field(min_length=1, max_length=32)


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    purpose: str
    purpose_version: str
    granted: bool
    granted_at: datetime
    revoked_at: datetime | None
