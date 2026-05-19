"""Process-session trigger endpoint integration tests.

Covers POST /sessions/{sid}/process — the API hook that enqueues
the ProcessSession Temporal workflow (per ADR-0007). The actual
workflow execution is tested separately via
`tests/test_workflow_process_session.py`; this suite asserts the
endpoint's behaviour against an in-memory recording workflow
client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db import get_app_engine
from app.models import OrgKind, Session
from app.models.tenancy import Account, Org
from app.services.auth import Principal, issue_token
from app.services.workflows import (
    WorkflowRunHandle,
    set_workflows_client,
)


@dataclass(slots=True)
class _RecordingWorkflowsClient:
    """Captures every enqueue + returns a deterministic handle so
    the assertions can pin down the wire shape that landed on
    the workflow service."""

    calls: list[dict[str, object]] = field(default_factory=list)
    task_queue: str = "test-post-session"

    async def start_process_session(
        self,
        *,
        session_id: str,
        partial_session: bool,
        tenant_id: str,
    ) -> WorkflowRunHandle:
        self.calls.append(
            {
                "session_id": session_id,
                "partial_session": partial_session,
                "tenant_id": tenant_id,
            }
        )
        return WorkflowRunHandle(
            workflow_id=f"wf-{session_id}",
            task_queue=self.task_queue,
        )


@pytest.fixture()
def workflows_client():
    fake = _RecordingWorkflowsClient()
    set_workflows_client(fake)
    yield fake
    set_workflows_client(None)


async def _signup_and_login(
    client: AsyncClient, email: str, *, role: str = "coach"
) -> tuple[str, str]:
    sr = await client.post(
        "/auth/signup",
        json={"email": email, "password": "p4ssw0rd!1234", "display_name": email.split("@")[0]},
    )
    assert sr.status_code == 201, sr.text
    user_id = sr.json()["id"]
    token, _ = issue_token(Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role=role))
    return token, user_id


async def _seed_session(user_id: str) -> str:
    sm = async_sessionmaker(get_app_engine(), expire_on_commit=False)
    tenant = f"solo:{user_id}"
    sid = f"sess-{user_id}"
    async with sm() as s, s.begin():
        s.add(Account(id=f"acc-{user_id}", name="acc", is_active=True))
        s.add(Org(id=f"org-{user_id}", kind=OrgKind.solo, name="solo", tenant_id=tenant))
        s.add(
            Session(
                id=sid,
                org_id=f"org-{user_id}",
                athlete_user_id=user_id,
                started_at=datetime.now(UTC),
                tenant_id=tenant,
            )
        )
    return sid


@pytest.mark.asyncio
async def test_trigger_process_session_returns_workflow_handle(
    client: AsyncClient, workflows_client: _RecordingWorkflowsClient
) -> None:
    token, user_id = await _signup_and_login(client, "proc-coach1@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/process",
        headers={"Authorization": f"Bearer {token}"},
        json={"partial_session": False},
    )
    assert r.status_code == 202, r.text
    out = r.json()
    assert out == {
        "session_id": sid,
        "workflow_id": f"wf-{sid}",
        "task_queue": "test-post-session",
    }
    assert workflows_client.calls == [
        {
            "session_id": sid,
            "partial_session": False,
            "tenant_id": f"solo:{user_id}",
        }
    ]


@pytest.mark.asyncio
async def test_trigger_process_session_threads_partial_flag(
    client: AsyncClient, workflows_client: _RecordingWorkflowsClient
) -> None:
    token, user_id = await _signup_and_login(client, "proc-coach2@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/process",
        headers={"Authorization": f"Bearer {token}"},
        json={"partial_session": True},
    )
    assert r.status_code == 202
    assert workflows_client.calls[0]["partial_session"] is True


@pytest.mark.asyncio
async def test_trigger_process_session_default_partial_false(
    client: AsyncClient, workflows_client: _RecordingWorkflowsClient
) -> None:
    """Empty payload → partial_session defaults to False."""
    token, user_id = await _signup_and_login(client, "proc-coach3@example.com")
    sid = await _seed_session(user_id)

    r = await client.post(
        f"/sessions/{sid}/process",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert r.status_code == 202
    assert workflows_client.calls[0]["partial_session"] is False


@pytest.mark.asyncio
async def test_trigger_process_session_404_missing_session(
    client: AsyncClient, workflows_client: _RecordingWorkflowsClient
) -> None:
    """Missing session → 404, and the workflow service is NOT
    called. The endpoint must validate before enqueuing."""
    token, _ = await _signup_and_login(client, "proc-coach4@example.com")

    r = await client.post(
        "/sessions/sess-does-not-exist/process",
        headers={"Authorization": f"Bearer {token}"},
        json={"partial_session": False},
    )
    assert r.status_code == 404
    assert workflows_client.calls == []


@pytest.mark.asyncio
async def test_trigger_process_session_cross_tenant_404(
    client: AsyncClient, workflows_client: _RecordingWorkflowsClient
) -> None:
    _, user_a = await _signup_and_login(client, "procA@example.com")
    sid = await _seed_session(user_a)

    token_b, _ = await _signup_and_login(client, "procB@example.com")
    r = await client.post(
        f"/sessions/{sid}/process",
        headers={"Authorization": f"Bearer {token_b}"},
        json={"partial_session": False},
    )
    assert r.status_code == 404
    assert workflows_client.calls == []


@pytest.mark.asyncio
async def test_trigger_process_session_athlete_403(
    client: AsyncClient, workflows_client: _RecordingWorkflowsClient
) -> None:
    """Athletes don't trigger post-session processing — coaches do.
    Athlete tier bounces 403, and the workflow service is not called."""
    _, user_id = await _signup_and_login(client, "proc-coach5@example.com")
    sid = await _seed_session(user_id)

    ath_token, _ = issue_token(
        Principal(user_id=user_id, tenant_id=f"solo:{user_id}", role="athlete")
    )
    r = await client.post(
        f"/sessions/{sid}/process",
        headers={"Authorization": f"Bearer {ath_token}"},
        json={"partial_session": False},
    )
    assert r.status_code == 403
    assert workflows_client.calls == []


@pytest.mark.asyncio
async def test_default_logging_client_returns_workflow_id_with_session(
    client: AsyncClient,
) -> None:
    """Without the test-override fixture, the default
    LoggingWorkflowsClient is used. It returns a workflow id that
    begins with `process-session-<sid>-` — sanity check that the
    real default path doesn't 500."""
    token, user_id = await _signup_and_login(client, "proc-coach6@example.com")
    sid = await _seed_session(user_id)
    set_workflows_client(None)  # ensure default

    r = await client.post(
        f"/sessions/{sid}/process",
        headers={"Authorization": f"Bearer {token}"},
        json={"partial_session": False},
    )
    assert r.status_code == 202, r.text
    out = r.json()
    assert out["session_id"] == sid
    assert out["workflow_id"].startswith(f"process-session-{sid}-")
    assert out["task_queue"] == "aimvision-post-session"
