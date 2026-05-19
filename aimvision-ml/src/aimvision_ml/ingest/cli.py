"""`aimvision-ml ingest` CLI — operator-facing wrappers around the
backend ingest client.

These commands let an operator (or a cron / Temporal activity shell
in the interim before the worker is wired) push results to the
backend without writing Python. The two commands shipped here —
`post-shot` and `finalize-session` — don't depend on any ML
inference, so they're useful as smoke-tests of the backend's
ingest path against a live deployment.

The `run-post-session` command runs the *real* spectral-flux shot
detector over a WAV file and pushes detected shots to the backend —
the genuine end-to-end ingest path (the input audio is the only
thing supplied externally).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from .backend_client import (
    BackendClient,
    BackendError,
    SessionEndPayload,
    ShotPayload,
)
from .post_session import run_post_session


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


@ingest.command("run-post-session")
@_backend_url
@_token
@click.option("--session-id", required=True)
@click.option(
    "--audio",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="WAV file of the session audio to run shot detection over.",
)
@click.option(
    "--diagnostic-model",
    default=None,
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    help="Optional ONNX diagnostic-head model. Skipped if absent (audio-only).",
)
def run_post_session_cmd(
    backend_url: str,
    token: str,
    session_id: str,
    audio: Path,
    diagnostic_model: Path | None,
) -> None:
    """Run the real post-session pipeline over a WAV file.

    Detects shots with the spectral-flux onset detector, POSTs each to
    the backend, optionally runs the diagnostic head (when a model is
    given), and finalizes the session. With no model, the session is
    finalized as `partial` (audio-only).
    """
    import numpy as np
    from scipy.io import wavfile

    from aimvision_ml.inference.diagnostic_onnx import DiagnosticOnnxModel

    sample_rate, raw = wavfile.read(str(audio))
    # Normalize integer PCM to float32 in [-1, 1]; pass float through.
    if np.issubdtype(raw.dtype, np.integer):
        max_val = float(np.iinfo(raw.dtype).max)
        pcm = (raw.astype(np.float32) / max_val).astype(np.float32)
    else:
        pcm = raw.astype(np.float32)
    if pcm.ndim > 1:  # stereo → mono
        pcm = pcm.mean(axis=1).astype(np.float32)

    diag = DiagnosticOnnxModel.load_or_none(diagnostic_model)

    async def _run_pipeline() -> dict[str, object]:
        async with BackendClient(backend_url, token) as client:
            result = await run_post_session(
                client,
                session_id,
                pcm,
                int(sample_rate),
                diagnostic_model=diag,
            )
            return {
                "session_id": result.session_id,
                "shots_detected": result.shots_detected,
                "shots_posted": result.shots_posted,
                "diagnostic_events_posted": result.diagnostic_events_posted,
                "partial_session": result.partial_session,
            }

    try:
        result = _run(_run_pipeline())
    except BackendError as e:
        raise click.ClickException(f"backend error {e.status_code}: {e.detail}") from e
    click.echo(json.dumps(result, indent=2))
