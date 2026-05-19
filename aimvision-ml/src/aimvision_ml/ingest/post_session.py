"""Post-session orchestration — the real end-to-end ingest flow.

This is the runtime a Temporal activity (or the operator CLI) drives:
take a session's audio, run the *real* spectral-flux shot detector,
push each detected shot to the backend, optionally run the diagnostic
head per shot, and finalize the session — all through `BackendClient`.

Unlike the backend's Temporal *workflow* (which is a separate
deployable and can only orchestrate, not run ML), this orchestrator
runs in the ML worker process where torch / onnxruntime / numpy live.
It processes real PCM with real algorithms and writes real rows; the
only thing synthetic in tests is the input waveform.

# Diagnostic gating

If `diagnostic_model` is None (the default — no trained weights ship,
see `diagnostic_onnx.load_or_none`), per-shot diagnostics are skipped
and the session is flagged `partial_session=True` so the report
renders an honest "audio-only" badge rather than fabricating
diagnostics.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import numpy.typing as npt

from aimvision_ml.inference.audio_shot import ShotEvent, SpectralFluxOnsetDetector
from aimvision_ml.inference.diagnostic_onnx import DiagnosticOnnxModel

from .backend_client import (
    BackendClient,
    SessionEndPayload,
    ShotEventPayload,
    ShotPayload,
)

# Feature extractor: shot + the session PCM → per-shot feature vector.
# The real implementation (per-shot pose/barrel/audio features) lives
# in the pipeline; callers inject it so this orchestrator stays
# decoupled from the feature schema.
FeatureFn = Callable[[ShotEvent, npt.NDArray[np.float32], int], npt.NDArray[np.float32]]


@dataclass(frozen=True, slots=True)
class PostSessionResult:
    session_id: str
    shots_detected: int
    shots_posted: int
    diagnostic_events_posted: int
    partial_session: bool


async def run_post_session(
    client: BackendClient,
    session_id: str,
    pcm: npt.NDArray[np.float32],
    sample_rate: int,
    *,
    device_clock_base_ns: int = 0,
    detector: SpectralFluxOnsetDetector | None = None,
    diagnostic_model: DiagnosticOnnxModel | None = None,
    feature_fn: FeatureFn | None = None,
    finalize: bool = True,
) -> PostSessionResult:
    """Run the real post-session ingest over a PCM buffer.

    1. Detect shots with the spectral-flux onset detector.
    2. POST each shot (monotonic_seq = detection order; device_clock_ns
       = base + the shot's timestamp). Idempotent backend-side.
    3. If a diagnostic model + feature_fn are supplied, run the head
       per shot and POST a `diagnostic.head_inference` event carrying
       the per-atom probabilities. Skipped (→ partial session) when no
       model is available.
    4. Finalize the session.
    """
    det = detector or SpectralFluxOnsetDetector()
    shots: list[ShotEvent] = det.detect(pcm, sample_rate)

    can_diagnose = diagnostic_model is not None and feature_fn is not None
    shots_posted = 0
    diagnostic_events = 0

    for seq, shot in enumerate(shots):
        device_clock_ns = device_clock_base_ns + int(shot.timestamp_s * 1_000_000_000)
        created = await client.post_shot(
            session_id,
            ShotPayload(monotonic_seq=seq, device_clock_ns=device_clock_ns),
        )
        shots_posted += 1

        if can_diagnose:
            assert diagnostic_model is not None and feature_fn is not None
            features = feature_fn(shot, pcm, sample_rate)
            probs = diagnostic_model.predict(features)
            await client.post_shot_event(
                session_id,
                str(created["id"]),
                ShotEventPayload(
                    event_kind="diagnostic.head_inference",
                    monotonic_seq=0,
                    payload={atom.value: prob for atom, prob in probs.items()},
                    produced_at=datetime.now(UTC),
                ),
            )
            diagnostic_events += 1

    # No diagnostics ran → the session is audio-only; flag it partial
    # so the report is honest about coverage (ml-architecture.md).
    partial = not can_diagnose

    if finalize:
        await client.patch_session_end(session_id, SessionEndPayload(partial_session=partial))

    return PostSessionResult(
        session_id=session_id,
        shots_detected=len(shots),
        shots_posted=shots_posted,
        diagnostic_events_posted=diagnostic_events,
        partial_session=partial,
    )
