"""Workflow enqueue abstraction (ADR-0007).

The post-session pipeline runs on Temporal (see
`app/workflows/process_session.py`). API endpoints that want to
*start* a workflow run depend on this service rather than the
Temporal SDK directly, so:

  1. Tests can inject an in-memory recorder without spinning up a
     dev cluster (slow + needs the embedded server). The Temporal
     workflow tests in `tests/test_workflow_process_session.py`
     already cover the actual workflow execution end-to-end via
     `WorkflowEnvironment.start_time_skipping`.
  2. The real Temporal client wiring can land in a follow-up
     slice without re-doing the endpoint surface.

The default `LoggingWorkflowsClient` records the enqueue request,
logs it, and returns a deterministic workflow id. It's safe for
dev and CI; it does not actually start a Temporal workflow. When
the production cluster is online, swap to
`TemporalWorkflowsClient` via `set_workflows_client(...)`.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger("aimvision.workflows")


@dataclass(frozen=True, slots=True)
class WorkflowRunHandle:
    """Reference to an enqueued workflow run. `workflow_id` is the
    durable id Temporal uses for cancellation, signalling, and
    history lookup; the Web UI displays the same value."""

    workflow_id: str
    task_queue: str


class WorkflowsClient(Protocol):
    """Abstract interface for the workflow runtime. The two known
    implementations: `LoggingWorkflowsClient` (default; logs the
    enqueue but doesn't actually start a run), and the future
    `TemporalWorkflowsClient` that wraps `temporalio.client.Client`.
    """

    async def start_process_session(
        self,
        *,
        session_id: str,
        partial_session: bool,
        tenant_id: str,
    ) -> WorkflowRunHandle: ...


class LoggingWorkflowsClient:
    """Stub implementation that logs the enqueue and returns a
    deterministic workflow id. Safe for dev + CI; this is what the
    backend boots with by default until the Temporal cluster is
    wired in production."""

    def __init__(self, *, task_queue: str = "aimvision-post-session") -> None:
        self._task_queue = task_queue

    async def start_process_session(
        self,
        *,
        session_id: str,
        partial_session: bool,
        tenant_id: str,
    ) -> WorkflowRunHandle:
        # Deterministic-ish workflow id: `process-session-<sid>-<short-uuid>`.
        # Including the session id at the front makes the Temporal UI
        # search trivial. The short uuid suffix lets a coach re-trigger
        # processing without colliding with the previous run.
        workflow_id = f"process-session-{session_id}-{uuid.uuid4().hex[:8]}"
        logger.info(
            "workflow.enqueue.stub",
            extra={
                "workflow_id": workflow_id,
                "session_id": session_id,
                "tenant_id": tenant_id,
                "partial_session": partial_session,
                "task_queue": self._task_queue,
            },
        )
        return WorkflowRunHandle(workflow_id=workflow_id, task_queue=self._task_queue)


_client: WorkflowsClient | None = None


def get_workflows_client() -> WorkflowsClient:
    """FastAPI dependency. Singleton default = `LoggingWorkflowsClient`.
    Tests + production wiring override via `set_workflows_client(...)`."""
    global _client
    if _client is None:
        _client = LoggingWorkflowsClient()
    return _client


def set_workflows_client(client: WorkflowsClient | None) -> None:
    """Set or clear the singleton client. Tests pass an in-memory
    recorder, then `set_workflows_client(None)` in teardown to reset."""
    global _client
    _client = client
