"""ProcessSessionWorkflow — ADR-0007 post-session pipeline.

The first first-class workflow per ADR. Triggered when a session's
recording uploads finish; chains the post-session activities in a
fixed order, with the spec'd retry policy applied at the workflow
boundary so individual activities don't have to think about it.

# Why the explicit dataclass input

A single str arg would work, but the ADR calls for "documented
input schema" per workflow and `workflow.patched()` for non-
backward-compatible changes. A dataclass is the lightest-weight
way to satisfy both: adding fields stays backward-compatible as
long as new fields default; signatures stay deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .activities import (
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


@dataclass(frozen=True, slots=True)
class ProcessSessionInput:
    session_id: str
    # The post-session worker can preemptively flag the session as
    # partial when the upstream signals indicate degraded capture
    # (e.g. one of the recordings is `phone_dev` source_kind, or a
    # GoPro disconnected mid-session). Default False keeps the
    # happy path tight.
    partial_session: bool = False
    # Tenant the session belongs to. The finalize activity mints a
    # service token scoped to this tenant to call the backend API.
    # Defaults to "" so callers that only orchestrate (and the stub
    # finalize path) stay backward-compatible.
    tenant_id: str = ""


@dataclass(frozen=True, slots=True)
class ProcessSessionResult:
    session_id: str
    alignment: AlignmentResult
    calibration: CalibrationResult
    shot_detection: ShotDetectionResult
    diagnostic: DiagnosticResult
    finalize: FinalizeResult
    # Activities executed in this run, in order. Lets the test suite
    # + Temporal Web UI inspect the pipeline progression without
    # parsing logs.
    steps_completed: tuple[str, ...] = field(default_factory=tuple)


# ADR-0007 §retry: initial_interval=1s, backoff_coefficient=2.0,
# maximum_interval=60s, maximum_attempts=10. Activities that touch
# external services (Anthropic, Stripe, S3) override the maxima
# with longer values; the stub activities below use the defaults.
_DEFAULT_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=10,
)

# Per-activity wall-clock budget. Sized generously — the goal is to
# let Temporal time-out a hung activity rather than to constrain a
# specific cost model.
_DEFAULT_TIMEOUT = timedelta(minutes=15)


@workflow.defn(name="ProcessSession")
class ProcessSessionWorkflow:
    """Post-session pipeline orchestrator. The activities are stubs
    today (see `app.workflows.activities.post_session`); a follow-up
    slice will wire them to the backend API."""

    @workflow.run
    async def run(self, payload: ProcessSessionInput) -> ProcessSessionResult:
        sid = payload.session_id

        alignment = await workflow.execute_activity(
            compute_alignment,
            args=[sid, f"{workflow.info().workflow_id}:alignment"],
            start_to_close_timeout=_DEFAULT_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

        calibration = await workflow.execute_activity(
            compute_calibration,
            args=[sid, f"{workflow.info().workflow_id}:calibration"],
            start_to_close_timeout=_DEFAULT_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

        shot_detection = await workflow.execute_activity(
            detect_shots,
            args=[sid, f"{workflow.info().workflow_id}:shots"],
            start_to_close_timeout=_DEFAULT_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

        diagnostic = await workflow.execute_activity(
            run_per_shot_diagnostic,
            args=[
                sid,
                shot_detection.shot_ids,
                f"{workflow.info().workflow_id}:diagnostic",
            ],
            start_to_close_timeout=_DEFAULT_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

        finalize = await workflow.execute_activity(
            finalize_session,
            args=[
                sid,
                payload.partial_session,
                payload.tenant_id,
                f"{workflow.info().workflow_id}:finalize",
            ],
            start_to_close_timeout=_DEFAULT_TIMEOUT,
            retry_policy=_DEFAULT_RETRY,
        )

        return ProcessSessionResult(
            session_id=sid,
            alignment=alignment,
            calibration=calibration,
            shot_detection=shot_detection,
            diagnostic=diagnostic,
            finalize=finalize,
            steps_completed=(
                "alignment",
                "calibration",
                "shot_detection",
                "diagnostic",
                "finalize",
            ),
        )
