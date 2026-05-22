"""ProcessSessionWorkflow integration tests via Temporal's time-
skipping test environment.

The environment runs an embedded dev server bundled with the
`temporalio` wheel (no Java, no Docker required). Activities run
exactly as deployed; the workflow timer accelerates so we don't
actually wait 15-minute timeouts in tests.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from temporalio.client import Client
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from app.services.ingest_client import IngestClient
from app.workflows import (
    ProcessSessionInput,
    ProcessSessionResult,
    ProcessSessionWorkflow,
)
from app.workflows.activities import (
    compute_alignment,
    compute_calibration,
    detect_shots,
    finalize_session,
    run_per_shot_diagnostic,
)
from app.workflows.activities import post_session as post_session_module

_TASK_QUEUE = "test-post-session"


async def _run(payload: ProcessSessionInput) -> ProcessSessionResult:
    """Spin up an isolated dev server, run the workflow end-to-end,
    return the typed result. Each test gets its own server +
    workflow id."""
    async with await WorkflowEnvironment.start_time_skipping() as env:
        client: Client = env.client
        worker = Worker(
            client,
            task_queue=_TASK_QUEUE,
            workflows=[ProcessSessionWorkflow],
            activities=[
                compute_alignment,
                compute_calibration,
                detect_shots,
                run_per_shot_diagnostic,
                finalize_session,
            ],
        )
        async with worker:
            result: ProcessSessionResult = await client.execute_workflow(
                ProcessSessionWorkflow.run,
                payload,
                id=f"wf-{uuid.uuid4().hex}",
                task_queue=_TASK_QUEUE,
            )
            return result


@pytest.mark.asyncio
async def test_workflow_chains_all_activities_in_order() -> None:
    """Happy path: workflow returns a result with every activity
    populated and `steps_completed` listing them in execution
    order. Confirms the scaffold's wiring is correct end-to-end."""
    result = await _run(ProcessSessionInput(session_id="sess-abc"))

    assert result.session_id == "sess-abc"
    assert result.steps_completed == (
        "alignment",
        "calibration",
        "shot_detection",
        "diagnostic",
        "finalize",
    )


@pytest.mark.asyncio
async def test_workflow_propagates_session_id_to_every_activity() -> None:
    """Every activity's result echoes the session_id from input.
    Catches accidental hardcoded ids."""
    result = await _run(ProcessSessionInput(session_id="sess-xyz"))

    assert result.alignment.session_id == "sess-xyz"
    assert result.calibration.session_id == "sess-xyz"
    assert result.shot_detection.session_id == "sess-xyz"
    assert result.diagnostic.session_id == "sess-xyz"
    assert result.finalize.session_id == "sess-xyz"


@pytest.mark.asyncio
async def test_workflow_threads_partial_session_flag_through_finalize() -> None:
    """`partial_session` flows from input through finalize_session.
    Mirrors the ADR's degraded-mode reporting requirement."""
    result = await _run(ProcessSessionInput(session_id="sess-partial", partial_session=True))

    assert result.finalize.partial_session is True


@pytest.mark.asyncio
async def test_workflow_uses_distinct_idempotency_keys_per_activity() -> None:
    """ADR-0007: every activity takes an explicit idempotency_key.
    The workflow scopes the key by workflow_id + activity name so
    re-execution of one activity in a retry storm doesn't collide
    with another. Different activity keys must be distinct within
    the same run."""
    result = await _run(ProcessSessionInput(session_id="sess-keys"))
    keys = {
        result.alignment.idempotency_key,
        result.calibration.idempotency_key,
        result.shot_detection.idempotency_key,
        result.diagnostic.idempotency_key,
        result.finalize.idempotency_key,
    }
    assert len(keys) == 5, "activities must share workflow_id but not the suffix"
    for k in keys:
        assert ":" in k, "idempotency_key should be workflow_id:activity_name"


@pytest.mark.asyncio
async def test_finalize_persists_to_backend_when_client_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a backend client is available, finalize_session actually
    PATCHes /sessions/{sid}/end with the partial flag and reports
    `persisted=True`. The stub path (no client) is the default the
    other tests exercise."""
    calls: list[tuple[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((str(request.url), request.read()))
        # Echo a minimal SessionOut-shaped body.
        return httpx.Response(200, json={"id": "sess-fin", "partial_session": True})

    def fake_make_client(tenant_id: str) -> IngestClient:
        assert tenant_id == "solo:t-1"
        return IngestClient(
            "http://backend.test",
            "svc-token",
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(post_session_module, "make_ingest_client", fake_make_client)

    result = await _run(
        ProcessSessionInput(session_id="sess-fin", partial_session=True, tenant_id="solo:t-1")
    )

    assert result.finalize.persisted is True
    assert result.finalize.partial_session is True
    assert len(calls) == 1
    url, body = calls[0]
    assert url.endswith("/sessions/sess-fin/end")
    assert b'"partial_session":true' in body.replace(b" ", b"")


@pytest.mark.asyncio
async def test_workflow_passes_detected_shot_ids_to_diagnostic() -> None:
    """The diagnostic activity must run against the actual shot ids
    surfaced by shot detection, not against a hardcoded list. A
    wiring bug here would silently drop the per-shot diagnostic
    coverage."""
    result = await _run(ProcessSessionInput(session_id="sess-shots"))

    assert result.shot_detection.shots_detected == 3
    assert result.diagnostic.shots_processed == result.shot_detection.shots_detected
