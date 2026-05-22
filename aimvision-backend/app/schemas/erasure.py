"""DTOs for the right-to-erasure endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ErasureRequestIn(BaseModel):
    athlete_user_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=255)


class ErasureTicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    athlete_user_id: str
    requested_by: str
    reason: str
    status: str
    references: dict[str, int] | None = Field(default=None, validation_alias="references_json")
    created_at: datetime
    completed_at: datetime | None = None
