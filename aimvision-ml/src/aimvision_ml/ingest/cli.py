"""`aimvision-ml ingest` CLI — operator-facing wrappers around the
backend ingest client.

These commands let an operator (or a cron / Temporal activity shell
in the interim before the worker is wired) push results to the
backend without writing Python. The two commands shipped here —
`post-shot` and `finalize-session` — don't depend on any ML
inference, so they're useful as smoke-tests of the backend's
ingest path against a live deployment.

The alignment / calibration / diagnostic ingest commands will land
once the corresponding ML inference is runnable end-to-end
(currently gated on hardware + GPU data).
"""

from __future__ import annotations

import asyncio
import json

import click

from .backend_client import (
    BackendClient,
    BackendError,
    SessionEndPayload,
    ShotPayload,
)


def _run(coro: object) -> object:
    # Small indirection so tests can monkeypatch the runner if needed.
    return asyncio.run(coro)  # type: ignore[arg-type]


@click.group()
def ingest() -> None:
    """Push post-session results to the AIMVISION backend."""


_backend_url = click.option(
    "--backend-url",
    required=True,
    envvar="AIMVISION_BACKEND_URL",
    help="Base URL of the backend API. Reads AIMVISION_BACKEND_URL if unset.",
)
_token = click.option(
    "--token",
    required=True,
    envvar="AIMVISION_BACKEND_TOKEN",
    help="Bearer token for a coach-tier principal. Reads AIMVISION_BACKEND_TOKEN if unset.",
)


@ingest.command("post-shot")
@_backend_url
@_token
@click.option("--session-id", required=True)
@click.option("--monotonic-seq", type=int, required=True)
@click.option("--device-clock-ns", type=int, required=True)
@click.option("--kind", default="single", show_default=True)
def post_shot_cmd(
    backend_url: str,
    token: str,
    session_id: str,
    monotonic_seq: int,
    device_clock_ns: int,
    kind: str,
) -> None:
    """Ingest a single detected shot into a session's shot stream.

    Idempotent on (session_id, monotonic_seq) backend-side, so re-
    running with the same seq is safe.
    """

    async def _go() -> dict[str, object]:
        async with BackendClient(backend_url, token) as client:
            return await client.post_shot(
                session_id,
                ShotPayload(
                    monotonic_seq=monotonic_seq,
                    device_clock_ns=device_clock_ns,
                    shot_kind=kind,
                ),
            )

    try:
        result = _run(_go())
    except BackendError as e:
        raise click.ClickException(f"backend error {e.status_code}: {e.detail}") from e
    click.echo(json.dumps(result, indent=2))


@ingest.command("finalize-session")
@_backend_url
@_token
@click.option("--session-id", required=True)
@click.option(
    "--partial/--no-partial",
    default=False,
    show_default=True,
    help="Flag the session as degraded-mode (incomplete diagnostic coverage).",
)
def finalize_session_cmd(
    backend_url: str,
    token: str,
    session_id: str,
    partial: bool,
) -> None:
    """Close out a session's lifecycle (PATCH /sessions/{sid}/end)."""

    async def _go() -> dict[str, object]:
        async with BackendClient(backend_url, token) as client:
            return await client.patch_session_end(
                session_id,
                SessionEndPayload(partial_session=partial),
            )

    try:
        result = _run(_go())
    except BackendError as e:
        raise click.ClickException(f"backend error {e.status_code}: {e.detail}") from e
    click.echo(json.dumps(result, indent=2))
