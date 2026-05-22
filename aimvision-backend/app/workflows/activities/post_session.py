"""Post-session activity stubs.

Each activity owns one HTTP-equivalent step in the ADR-0007 §
post-session pipeline. The current implementations are stubs: they
log the call, validate inputs, and return a deterministic result
derived from the inputs (so workflow tests can assert on the chain
without needing a live backend).

Future slices replace the stub body with httpx calls to the backend
endpoints landed in PRs #53-#63: PATCH /alignment, POST /calibration,
POST /shots, POST /events, PATCH /end.

# Idempotency

Per ADR-0007: every activity takes an `idempotency_key` and is safe
to re-execute. Temporal retries activities on transient failure;
non-idempotent activities corrupt state. The stub already accepts +
echoes the key so the workflow contract is correct from day one.
"""

from __future__ import annotations

from dataclasses import dataclass

from temporalio import activity

from app.config import get_settings
from app.services.auth import Principal, issue_token
from app.services.ingest_client import IngestClient


@dataclass(frozen=True, slots=True)
class AlignmentResult:
    session_id: str
    recordings_aligned: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    session_id: str
    recordings_calibrated: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ShotDetectionResult:
    session_id: str
    shots_detected: int
    shot_ids: tuple[str, ...]
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    session_id: str
    shots_processed: int
    events_emitted: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class FinalizeResult:
    session_id: str
    partial_session: bool
    idempotency_key: str
    # True when the activity actually called the backend and persisted
    # the session-end transition; False on the stub path (no
    # `post_session_base_url` configured — dev/CI default).
    persisted: bool = False


def make_ingest_client(tenant_id: str) -> IngestClient | None:
    """Build a backend client for the post-session worker, or None
    when no backend URL is configured (the stub path).

    Mints a coach-tier service token scoped to `tenant_id` signed with
    the backend's own `jwt_secret` — same trust domain, so the API
    accepts it. Indirected through a module function so tests can
    monkeypatch it to inject an httpx.MockTransport-backed client.
    """
    settings = get_settings()
    if not settings.post_session_base_url:
        return None
    token, _ = issue_token(
        Principal(
            user_id=settings.post_session_worker_user_id,
            tenant_id=tenant_id,
            role="coach",
        ),
        settings=settings,
    )
    return IngestClient(settings.post_session_base_url, token)


@activity.defn
async def compute_alignment(session_id: str, idempotency_key: str) -> AlignmentResult:
    """Run audio cross-correlation alignment across recordings.

    Stub: returns AlignmentResult(recordings_aligned=2). The next
    slice replaces this body with a backend call that:

      1. GETs /sessions/{sid}/recording to list recordings,
      2. For each pair, runs aimvision_ml.inference.audio_xcorr,
      3. PATCHes the offset+confidence onto each recording.
    """
    activity.logger.info(
        "compute_alignment.stub",
        extra={"session_id": session_id, "idempotency_key": idempotency_key},
    )
    return AlignmentResult(
        session_id=session_id,
        recordings_aligned=2,
        idempotency_key=idempotency_key,
    )


@activity.defn
async def compute_calibration(session_id: str, idempotency_key: str) -> CalibrationResult:
    """Run ChArUco bundle adjustment per recording.

    Stub: returns CalibrationResult(recordings_calibrated=2). The
    next slice wires this to aimvision_ml.inference.camera_calibration
    and POSTs to /sessions/{sid}/recording/{rid}/calibration.
    """
    activity.logger.info(
        "compute_calibration.stub",
        extra={"session_id": session_id, "idempotency_key": idempotency_key},
    )
    return CalibrationResult(
        session_id=session_id,
        recordings_calibrated=2,
        idempotency_key=idempotency_key,
    )


@activity.defn
async def detect_shots(session_id: str, idempotency_key: str) -> ShotDetectionResult:
    """Run the classical audio shot detector on the session audio.

    Stub: returns three synthetic shot ids. The next slice runs the
    detector from aimvision-ml/.../audio_shot_detector against the
    actual recording and POSTs to /sessions/{sid}/shots.
    """
    activity.logger.info(
        "detect_shots.stub",
        extra={"session_id": session_id, "idempotency_key": idempotency_key},
    )
    return ShotDetectionResult(
        session_id=session_id,
        shots_detected=3,
        shot_ids=("shot-stub-0", "shot-stub-1", "shot-stub-2"),
        idempotency_key=idempotency_key,
    )


@activity.defn
async def run_per_shot_diagnostic(
    session_id: str, shot_ids: tuple[str, ...], idempotency_key: str
) -> DiagnosticResult:
    """Run the diagnostic-head ensemble over the detected shots.

    Stub: emits one synthetic event per shot. The next slice runs
    the full multi-task hierarchical head from ml-architecture.md
    §8 and POSTs the calibrated probabilities to
    /sessions/{sid}/shots/{shot_id}/events with namespaced
    event_kind values (`diagnostic.*`).
    """
    activity.logger.info(
        "run_per_shot_diagnostic.stub",
        extra={
            "session_id": session_id,
            "shot_count": len(shot_ids),
            "idempotency_key": idempotency_key,
        },
    )
    return DiagnosticResult(
        session_id=session_id,
        shots_processed=len(shot_ids),
        events_emitted=len(shot_ids),
        idempotency_key=idempotency_key,
    )


@activity.defn
async def finalize_session(
    session_id: str, partial_session: bool, tenant_id: str, idempotency_key: str
) -> FinalizeResult:
    """Close the session lifecycle via PATCH /sessions/{sid}/end.

    When `post_session_base_url` is configured, this calls the backend
    API to set `ended_at` + the partial flag (idempotent on the
    backend). With no URL configured (dev/CI) it falls back to a
    log-only stub so the workflow chain still exercises end-to-end.
    """
    client = make_ingest_client(tenant_id)
    if client is None:
        activity.logger.info(
            "finalize_session.stub",
            extra={
                "session_id": session_id,
                "partial_session": partial_session,
                "idempotency_key": idempotency_key,
            },
        )
        return FinalizeResult(
            session_id=session_id,
            partial_session=partial_session,
            idempotency_key=idempotency_key,
            persisted=False,
        )

    activity.logger.info(
        "finalize_session.persist",
        extra={
            "session_id": session_id,
            "partial_session": partial_session,
            "idempotency_key": idempotency_key,
        },
    )
    async with client:
        await client.patch_session_end(session_id, partial_session=partial_session)
    return FinalizeResult(
        session_id=session_id,
        partial_session=partial_session,
        idempotency_key=idempotency_key,
        persisted=True,
    )
