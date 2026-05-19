"""End-to-end post-session ingest over real (synthetic) audio.

Drives `run_post_session` with the *real* spectral-flux shot
detector against a synthesized muzzle-blast clip, and a
MockTransport-backed BackendClient. Asserts the detected shots
actually flow through to POST /shots and the session is finalized.

The waveform is synthetic (no recorded range audio needed) but the
detection + the HTTP calls are real — this is the genuine pipeline,
not stubbed numbers.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import numpy as np
import pytest

from aimvision_ml.eval.synth_audio import synth_clip
from aimvision_ml.inference.diagnostic_onnx import NUM_ATOMS, DiagnosticOnnxModel
from aimvision_ml.ingest import BackendClient, run_post_session


def _recording_transport(
    calls: list[tuple[str, str, dict[str, Any] | None]],
) -> httpx.MockTransport:
    def _route(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        calls.append((request.method, request.url.path, body))
        # POST /shots returns a row with an id; everything else 200 {}.
        if request.url.path.endswith("/shots") and request.method == "POST":
            seq = body["monotonic_seq"] if body else 0
            return httpx.Response(201, json={"id": f"shot-{seq}", "monotonic_seq": seq})
        if request.url.path.endswith("/events") and request.method == "POST":
            return httpx.Response(201, json={"id": "ev-1"})
        return httpx.Response(200, json={"ok": True})

    return httpx.MockTransport(_route)


@pytest.mark.asyncio
async def test_run_post_session_posts_detected_shots_and_finalizes() -> None:
    # Real synthetic clip: 3 muzzle blasts in pink noise.
    clip = synth_clip(duration_s=4.0, n_shots=3, n_clay=2, rng=np.random.default_rng(11))
    truth_shots = [e for e in clip.events if e.kind == "shot"]

    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    async with BackendClient(
        "http://api.example.com", "tok", transport=_recording_transport(calls)
    ) as client:
        result = await run_post_session(
            client,
            "sess-e2e",
            clip.pcm,
            clip.sample_rate,
        )

    # The real detector ran and found roughly the right number of shots.
    assert result.shots_detected >= 1
    assert result.shots_posted == result.shots_detected
    # No diagnostic model supplied → audio-only → partial session.
    assert result.diagnostic_events_posted == 0
    assert result.partial_session is True

    shot_posts = [c for c in calls if c[1].endswith("/shots") and c[0] == "POST"]
    assert len(shot_posts) == result.shots_detected
    # monotonic_seq is the detection order: 0,1,2,...
    seqs = [c[2]["monotonic_seq"] for c in shot_posts if c[2]]
    assert seqs == list(range(len(seqs)))
    # device_clock_ns is monotonically increasing (shots are time-ordered).
    device_ns = [c[2]["device_clock_ns"] for c in shot_posts if c[2]]
    assert device_ns == sorted(device_ns)
    # The session was finalized as partial.
    end_calls = [c for c in calls if c[1].endswith("/end") and c[0] == "PATCH"]
    assert len(end_calls) == 1
    assert end_calls[0][2] == {"partial_session": True}

    # Sanity: detection count is in the right ballpark vs. ground truth.
    assert abs(result.shots_detected - len(truth_shots)) <= 2


@pytest.mark.asyncio
async def test_run_post_session_runs_diagnostics_when_model_present(
    tmp_path: Any,
) -> None:
    """With a diagnostic model + feature_fn, each shot also gets a
    `diagnostic.head_inference` event, and the session is NOT partial.
    Uses a hand-authored tiny ONNX model (no committed weights)."""
    pytest.importorskip("onnx")

    # Author a tiny diagnostic model (same helper shape as the onnx test).
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    feature_dim = 4
    w = (np.random.default_rng(0).standard_normal((feature_dim, NUM_ATOMS)) * 0.1).astype(
        np.float32
    )
    b = np.zeros((NUM_ATOMS,), dtype=np.float32)
    inp = helper.make_tensor_value_info("features", TensorProto.FLOAT, ["batch", feature_dim])
    out = helper.make_tensor_value_info("probabilities", TensorProto.FLOAT, ["batch", NUM_ATOMS])
    graph = helper.make_graph(
        [
            helper.make_node("MatMul", ["features", "W"], ["xw"]),
            helper.make_node("Add", ["xw", "B"], ["logits"]),
            helper.make_node("Sigmoid", ["logits"], ["probabilities"]),
        ],
        "head",
        [inp],
        [out],
        initializer=[numpy_helper.from_array(w, "W"), numpy_helper.from_array(b, "B")],
    )
    model_proto = helper.make_model(graph, opset_imports=[helper.make_operatorsetid("", 17)])
    model_proto.ir_version = 10
    onnx.checker.check_model(model_proto)
    model_path = tmp_path / "head.onnx"
    onnx.save(model_proto, str(model_path))

    diag = DiagnosticOnnxModel.load(model_path)
    clip = synth_clip(duration_s=3.0, n_shots=2, n_clay=0, rng=np.random.default_rng(5))

    def _feature_fn(shot: Any, pcm: Any, sample_rate: int) -> np.ndarray:
        # Toy feature vector — the real extractor lives in the pipeline.
        return np.array(
            [shot.timestamp_s, shot.confidence, float(shot.chunk_index), 1.0],
            dtype=np.float32,
        )

    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    async with BackendClient(
        "http://api.example.com", "tok", transport=_recording_transport(calls)
    ) as client:
        result = await run_post_session(
            client,
            "sess-diag",
            clip.pcm,
            clip.sample_rate,
            diagnostic_model=diag,
            feature_fn=_feature_fn,
        )

    assert result.shots_detected >= 1
    assert result.diagnostic_events_posted == result.shots_detected
    assert result.partial_session is False
    event_posts = [c for c in calls if c[1].endswith("/events") and c[0] == "POST"]
    assert len(event_posts) == result.shots_detected
    # Each diagnostic event carries one probability per atom.
    first = event_posts[0][2]
    assert first is not None
    assert first["event_kind"] == "diagnostic.head_inference"
    assert len(first["payload"]) == NUM_ATOMS


@pytest.mark.asyncio
async def test_run_post_session_no_shots_still_finalizes() -> None:
    """Silent clip → no shots, but the session is still finalized
    (as partial) so it doesn't hang in 'processing'."""
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    silent = np.zeros(48_000, dtype=np.float32)
    async with BackendClient(
        "http://api.example.com", "tok", transport=_recording_transport(calls)
    ) as client:
        result = await run_post_session(client, "sess-silent", silent, 48_000)

    assert result.shots_detected == 0
    assert result.shots_posted == 0
    end_calls = [c for c in calls if c[1].endswith("/end")]
    assert len(end_calls) == 1
