"""Session / Recording / Shot DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    # ADR-0009 slice 4: multi-camera alignment from audio xcorr. Both
    # fields NULL until the post-session Temporal worker writes them
    # via the alignment PATCH endpoint.
    session_clock_offset_ns: int | None = None
    session_clock_offset_confidence: float | None = None


class AlignmentIn(BaseModel):
    """Payload for the PATCH alignment endpoint.

    Both fields are required because writing the offset without its
    confidence — or vice versa — leaves the recording in a partial
    state that downstream consumers would have to guard against. The
    Temporal worker fills both atomically.
    """

    session_clock_offset_ns: int = Field(
        ...,
        description=(
            "Signed nanosecond offset relative to the session's master "
            "recording (positive = this recording's clock runs later)."
        ),
    )
    session_clock_offset_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Normalized cross-correlation coefficient from audio_xcorr.PairAlignment in [0, 1]."
        ),
    )


class ShotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    monotonic_seq: int
    shot_kind: str
