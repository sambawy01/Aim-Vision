"""Backend ingest client + post-session orchestration.

Bridges the ML inference layer (`aimvision_ml.inference.*`) and the
backend API surface (PRs #53-#63: alignment PATCH, calibration POST,
shots POST, shot-events POST, session-end PATCH). The Temporal
workflow scaffolded in `aimvision-backend/app/workflows/` will
eventually drive these calls; the client + orchestrator here are
the runtime that workflow activities delegate to.
"""

from .backend_client import (
    AlignmentPayload,
    BackendClient,
    BackendError,
    CalibrationPayload,
    SessionEndPayload,
    ShotEventPayload,
    ShotPayload,
)
from .post_session import PostSessionResult, run_post_session

__all__ = [
    "AlignmentPayload",
    "BackendClient",
    "BackendError",
    "CalibrationPayload",
    "PostSessionResult",
    "SessionEndPayload",
    "ShotEventPayload",
    "ShotPayload",
    "run_post_session",
]
