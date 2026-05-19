"""Session / Recording / Shot DTOs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionCreateIn(BaseModel):
    """Payload for POST /sessions.

    The coach starts a session for an athlete inside their org.
    `org_id` is required because a coach can belong to multiple
    orgs (a club coach can also be a federation coach); the caller
    disambiguates rather than us guessing. The org must be in the
    caller's tenant — cross-tenant org ids return 404, not 403.

    `started_at` is optional; when omitted, the server stamps
    `now()` at create time. Letting the client supply a past
    timestamp lets the mobile app backfill sessions captured while
    offline.
    """

    athlete_user_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="The shooting athlete. Must exist as a User row.",
    )
    org_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="The organisation under which the session is held. Must be in caller's tenant.",
    )
    discipline: str = Field(
        default="trap",
        max_length=64,
        description='Shooting discipline. "trap" / "skeet" / "sporting" etc.',
    )
    started_at: datetime | None = Field(
        default=None,
        description=(
            "When the session was started. Defaults to server `now()` if not "
            "supplied — the offline-backfill case overrides this."
        ),
    )


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    athlete_user_id: str
    discipline: str
    started_at: datetime
    ended_at: datetime | None
    # Degraded-mode flag per docs/ml-architecture.md.
    partial_session: bool = False


class SessionEndIn(BaseModel):
    """Payload for PATCH /sessions/{sid}/end.

    `partial_session` is optional — coaches and the post-session
    worker both end sessions. Coaches usually pass partial=False
    (the session was instrumented normally); the worker flips
    partial=True when its degraded-mode handler fired during
    processing.
    """

    partial_session: bool = Field(
        default=False,
        description=(
            "True iff the session had incomplete diagnostic coverage "
            "(e.g. GoPro died mid-session, audio-only fallback). The "
            "post-session report renders a 'partial' badge."
        ),
    )


class SessionSummaryOut(BaseModel):
    """Rolled-up readiness view over a session. Consumed by the
    post-session UI to decide whether to show the report or a "still
    processing" placeholder.

    Booleans are computed conservatively: `alignment_complete` is True
    only when *every* recording in the session has both alignment
    fields set OR the session has at most one recording (alignment is
    relative to a master recording, so a single recording is trivially
    aligned). `calibration_complete` is True when *every* recording
    has at least one calibration row.

    `recording_count` and `shot_count` are surfaced for the dashboard
    even before processing finishes — operators want to know "how big
    was this session?" right after the upload completes.
    """

    session_id: str
    recording_count: int
    shot_count: int
    calibration_count: int
    alignment_complete: bool
    calibration_complete: bool
    ended_at: datetime | None = None
    partial_session: bool = False


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


class ShotIn(BaseModel):
    """Payload for POST /sessions/{sid}/shots.

    The producer (audio shot detector, on-device camera-core, or the
    post-session Temporal worker) supplies the device-side timestamps
    plus the monotonic sequence number. The server stamps
    `server_clock_ns` at receipt. `shot_kind` defaults to "single"
    per the trap/skeet convention; "double" / "pair" are reserved
    for future doubles disciplines.
    """

    monotonic_seq: int = Field(
        ...,
        ge=0,
        description=(
            "Producer-side strictly-increasing sequence number within "
            "the session. (session_id, monotonic_seq) is the natural "
            "key; resubmits are idempotent."
        ),
    )
    device_clock_ns: int = Field(
        ...,
        ge=0,
        description="Producer's monotonic clock in nanoseconds at the detected shot.",
    )
    shot_kind: str = Field(
        default="single",
        max_length=32,
        description='"single" / "double" / "pair" — see Shot.shot_kind.',
    )


class ShotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    monotonic_seq: int
    device_clock_ns: int
    server_clock_ns: int
    shot_kind: str
    created_at: datetime


class ShotEventIn(BaseModel):
    """Payload for POST /sessions/{sid}/shots/{shot_id}/events.

    Per ADR-0006, ShotEvent is append-only. Multiple producers
    (audio detector, pose pipeline, diagnostic head, coach UI)
    write events to the same Shot. `event_kind` is a producer-
    namespaced string (e.g. "audio.shot_detected", "score.hit",
    "diagnostic.head_tilt"); `monotonic_seq` is per-producer and
    `(shot_id, event_kind, monotonic_seq)` is unique end-to-end.

    `payload` is free-form JSON whose schema is per-event-kind
    and documented in the producing service.
    """

    event_kind: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            'Producer-namespaced event kind. Example: "audio.shot_detected", '
            '"score.hit", "diagnostic.head_tilt".'
        ),
    )
    monotonic_seq: int = Field(
        ...,
        ge=0,
        description=(
            "Producer-side strictly-increasing sequence number scoped to "
            "(shot_id, event_kind). Resubmits are idempotent against the "
            "uq_shot_events_shot_kind_seq index."
        ),
    )
    payload: dict[str, object] = Field(
        ...,
        description=("Free-form JSON. Schema is per-event-kind and lives in the producer."),
    )
    produced_at: datetime = Field(
        ...,
        description=(
            "Producer's timestamp when the event was generated. Distinct from "
            "the row's `created_at` (DB insert time)."
        ),
    )


class ShotEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shot_id: str
    event_kind: str
    monotonic_seq: int
    payload: dict[str, object]
    produced_at: datetime
    created_at: datetime
