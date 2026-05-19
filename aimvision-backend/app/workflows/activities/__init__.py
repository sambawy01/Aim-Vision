"""Idempotent activity stubs for the post-session workflow (ADR-0007).

Activities follow the ADR's idempotency contract: each takes an
explicit `idempotency_key` (typically `workflow_id` + activity name)
and is safe to re-execute. The current stubs return canned results;
the next slice will wire them to the backend API surface added by
PRs #57-#63.
"""

from .post_session import (
    AlignmentResult,
    CalibrationResult,
    DiagnosticResult,
    FinalizeResult,
    ShotDetectionResult,
    compute_alignment,
    compute_calibration,
    detect_shots,
    finalize_session,
    run_per_shot_diagnostic,
)

__all__ = [
    "AlignmentResult",
    "CalibrationResult",
    "DiagnosticResult",
    "FinalizeResult",
    "ShotDetectionResult",
    "compute_alignment",
    "compute_calibration",
    "detect_shots",
    "finalize_session",
    "run_per_shot_diagnostic",
]
