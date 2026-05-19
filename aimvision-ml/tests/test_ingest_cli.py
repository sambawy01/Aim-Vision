"""Tests for the `aimvision-ml ingest` CLI.

Drives the click commands with CliRunner + monkeypatched BackendClient
so we exercise the argument plumbing + output formatting without a
live backend.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from click.testing import CliRunner

from aimvision_ml.__main__ import cli
from aimvision_ml.ingest import BackendError


class _FakeClient:
    """Stand-in BackendClient that records calls and returns canned
    responses. Implements just the async-context-manager surface +
    the two methods the CLI uses."""

    instances: list[_FakeClient] = []

    def __init__(self, base_url: str, token: str, **_: Any) -> None:
        self.base_url = base_url
        self.token = token
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        _FakeClient.instances.append(self)

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def post_shot(self, session_id: str, payload: object) -> dict[str, Any]:
        self.calls.append(("post_shot", (session_id, payload)))
        return {"id": "shot-1", "session_id": session_id}

    async def patch_session_end(
        self, session_id: str, payload: object | None = None
    ) -> dict[str, Any]:
        self.calls.append(("patch_session_end", (session_id, payload)))
        return {"id": session_id, "ended_at": "2026-05-20T10:00:00Z"}


@pytest.fixture()
def fake_client(monkeypatch: pytest.MonkeyPatch):
    _FakeClient.instances = []
    monkeypatch.setattr("aimvision_ml.ingest.cli.BackendClient", _FakeClient)
    return _FakeClient


def test_post_shot_command_happy_path(fake_client: type[_FakeClient]) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ingest",
            "post-shot",
            "--backend-url",
            "http://api.example.com",
            "--token",
            "tok",
            "--session-id",
            "sess-1",
            "--monotonic-seq",
            "0",
            "--device-clock-ns",
            "12345",
        ],
    )
    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert out["id"] == "shot-1"
    # Client was constructed with the supplied url + token.
    inst = fake_client.instances[-1]
    assert inst.base_url == "http://api.example.com"
    assert inst.token == "tok"
    name, args = inst.calls[0]
    assert name == "post_shot"
    assert args[0] == "sess-1"
    assert args[1].monotonic_seq == 0
    assert args[1].device_clock_ns == 12345
    assert args[1].shot_kind == "single"


def test_post_shot_command_reads_env(
    fake_client: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """--backend-url / --token fall back to env vars."""
    monkeypatch.setenv("AIMVISION_BACKEND_URL", "http://env.example.com")
    monkeypatch.setenv("AIMVISION_BACKEND_TOKEN", "env-tok")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ingest",
            "post-shot",
            "--session-id",
            "sess-env",
            "--monotonic-seq",
            "3",
            "--device-clock-ns",
            "9",
        ],
    )
    assert result.exit_code == 0, result.output
    inst = fake_client.instances[-1]
    assert inst.base_url == "http://env.example.com"
    assert inst.token == "env-tok"


def test_finalize_session_command_threads_partial(fake_client: type[_FakeClient]) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ingest",
            "finalize-session",
            "--backend-url",
            "http://api.example.com",
            "--token",
            "tok",
            "--session-id",
            "sess-2",
            "--partial",
        ],
    )
    assert result.exit_code == 0, result.output
    inst = fake_client.instances[-1]
    name, args = inst.calls[0]
    assert name == "patch_session_end"
    assert args[0] == "sess-2"
    assert args[1].partial_session is True


def test_finalize_session_defaults_no_partial(fake_client: type[_FakeClient]) -> None:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ingest",
            "finalize-session",
            "--backend-url",
            "http://api.example.com",
            "--token",
            "tok",
            "--session-id",
            "sess-3",
        ],
    )
    assert result.exit_code == 0, result.output
    inst = fake_client.instances[-1]
    assert inst.calls[0][1][1].partial_session is False


def test_run_post_session_command_detects_and_posts(
    fake_client: type[_FakeClient], tmp_path: Any
) -> None:
    """run-post-session reads a WAV, runs the real detector, and POSTs
    each detected shot + finalizes. Uses a synthesized clip written to
    a WAV file."""
    import numpy as np
    from scipy.io import wavfile

    from aimvision_ml.eval.synth_audio import synth_clip

    clip = synth_clip(duration_s=3.0, n_shots=2, n_clay=0, rng=np.random.default_rng(3))
    wav_path = tmp_path / "session.wav"
    # Write int16 PCM so the CLI's integer-normalization path is exercised.
    pcm_i16 = np.clip(clip.pcm * 32767.0, -32768, 32767).astype(np.int16)
    wavfile.write(str(wav_path), clip.sample_rate, pcm_i16)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ingest",
            "run-post-session",
            "--backend-url",
            "http://api.example.com",
            "--token",
            "tok",
            "--session-id",
            "sess-cli",
            "--audio",
            str(wav_path),
        ],
    )
    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert out["session_id"] == "sess-cli"
    assert out["shots_detected"] >= 1
    assert out["shots_posted"] == out["shots_detected"]
    assert out["partial_session"] is True  # no model → audio-only

    inst = fake_client.instances[-1]
    post_shots = [c for c in inst.calls if c[0] == "post_shot"]
    finalize = [c for c in inst.calls if c[0] == "patch_session_end"]
    assert len(post_shots) == out["shots_detected"]
    assert len(finalize) == 1


def test_backend_error_becomes_click_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """A BackendError surfaces as a non-zero exit + a clean message,
    not a traceback."""

    class _ErrClient(_FakeClient):
        async def patch_session_end(
            self, session_id: str, payload: object | None = None
        ) -> dict[str, Any]:
            raise BackendError(404, {"detail": "session not found"})

    monkeypatch.setattr("aimvision_ml.ingest.cli.BackendClient", _ErrClient)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "ingest",
            "finalize-session",
            "--backend-url",
            "http://api.example.com",
            "--token",
            "tok",
            "--session-id",
            "missing",
        ],
    )
    assert result.exit_code != 0
    assert "backend error 404" in result.output
