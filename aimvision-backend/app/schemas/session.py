"""Session / Recording / Shot DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    athlete_user_id: str
    discipline: str
    started_at: datetime
    ended_at: datetime | None


class RecordingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    storage_uri: str
    sha256: str | None
    duration_ms: int | None
    upload_state: str
    # ADR-0009: phone_dev tagged separately so report aggregations
    # can filter dev-mode captures out of customer-facing rollups.
    source_kind: str


class ShotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    monotonic_seq: int
    shot_kind: str
