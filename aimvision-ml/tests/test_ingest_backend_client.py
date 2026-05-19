"""Tests for `aimvision_ml.ingest.backend_client`.

The client wraps the backend ingest endpoints landed in backend
PRs #53-#63. These tests drive it with `httpx.MockTransport` so we
exercise the full request shape + response handling without
needing the actual FastAPI server up.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from aimvision_ml.ingest import (
    AlignmentPayload,
    BackendClient,
    BackendError,
    CalibrationPayload,
    SessionEndPayload,
    ShotEventPayload,
    ShotPayload,
)


def _mock_transport(
    handler: list[tuple[str, str, dict[str, Any] | None]],
    responses: list[httpx.Response],
) -> httpx.MockTransport:
    """Build a MockTransport that records every (method, path, body)
    the client sent, and returns the queued responses in order."""

    def _route(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        handler.append((request.method, request.url.path, body))
        return responses.pop(0)

    return httpx.MockTransport(_route)


def _ok(payload: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


@pytest.mark.asyncio
async def test_patch_alignment_sends_correct_shape() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    responses = [_ok({"id": "rec-1", "session_clock_offset_ns": 12345})]

    async with BackendClient(
        "http://api.example.com",
        "tok",
        transport=_mock_transport(calls, responses),
    ) as client:
        out = await client.patch_alignment(
            "sess-1",
            "rec-1",
            AlignmentPayload(session_clock_offset_ns=12345, session_clock_offset_confidence=0.91),
        )

    assert calls == [
        (
            "PATCH",
            "/sessions/sess-1/recording/rec-1/alignment",
            {"session_clock_offset_ns": 12345, "session_clock_offset_confidence": 0.91},
        )
    ]
    assert out["session_clock_offset_ns"] == 12345


@pytest.mark.asyncio
async def test_post_calibration_serialises_matrices_verbatim() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    responses = [_ok({"id": "cal-1"}, status=201)]

    payload = CalibrationPayload(
        intrinsics_k_json=[[1500.0, 0.0, 960.0], [0.0, 1500.0, 540.0], [0.0, 0.0, 1.0]],
        distortion_coeffs_json=[-0.05, 0.01, 0.0, 0.0, 0.0],
        extrinsics_r_json=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        extrinsics_t_json=[0.0, 0.0, 0.0],
        reprojection_error_px_p95=0.42,
        charuco_frames_used=12,
        calibration_ts_ns=1_700_000_000_000_000_000,
    )
    async with BackendClient(
        "http://api.example.com",
        "tok",
        transport=_mock_transport(calls, responses),
    ) as client:
        await client.post_calibration("sess-1", "rec-1", payload)

    assert calls[0][0] == "POST"
    assert calls[0][1] == "/sessions/sess-1/recording/rec-1/calibration"
    body = calls[0][2]
    assert body is not None
    # Matrix payloads preserved structurally — the wire shape must
    # match `CameraCalibrationIn` field-for-field.
    assert body["intrinsics_k_json"] == payload.intrinsics_k_json
    assert body["distortion_coeffs_json"] == payload.distortion_coeffs_json
    assert body["extrinsics_r_json"] == payload.extrinsics_r_json
    assert body["extrinsics_t_json"] == payload.extrinsics_t_json
    assert body["reprojection_error_px_p95"] == payload.reprojection_error_px_p95
    assert body["charuco_frames_used"] == payload.charuco_frames_used
    assert body["calibration_ts_ns"] == payload.calibration_ts_ns


@pytest.mark.asyncio
async def test_post_shot_includes_default_kind() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    responses = [_ok({"id": "shot-1"}, status=201)]

    async with BackendClient(
        "http://api.example.com",
        "tok",
        transport=_mock_transport(calls, responses),
    ) as client:
        await client.post_shot("sess-1", ShotPayload(monotonic_seq=0, device_clock_ns=12345))

    assert calls[0][2] == {
        "monotonic_seq": 0,
        "device_clock_ns": 12345,
        "shot_kind": "single",
    }


@pytest.mark.asyncio
async def test_post_shot_event_serialises_produced_at_iso8601() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    responses = [_ok({"id": "ev-1"}, status=201)]

    when = datetime(2026, 5, 19, 14, 30, tzinfo=UTC)
    async with BackendClient(
        "http://api.example.com",
        "tok",
        transport=_mock_transport(calls, responses),
    ) as client:
        await client.post_shot_event(
            "sess-1",
            "shot-1",
            ShotEventPayload(
                event_kind="diagnostic.head_tilt",
                monotonic_seq=0,
                payload={"prob": 0.81, "branch": "stance"},
                produced_at=when,
            ),
        )

    body = calls[0][2]
    assert body is not None
    assert body["event_kind"] == "diagnostic.head_tilt"
    assert body["produced_at"] == when.isoformat()
    assert body["payload"] == {"prob": 0.81, "branch": "stance"}


@pytest.mark.asyncio
async def test_patch_session_end_defaults_partial_false() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    responses = [_ok({"id": "sess-1", "ended_at": "2026-05-19T15:00:00Z"})]

    async with BackendClient(
        "http://api.example.com",
        "tok",
        transport=_mock_transport(calls, responses),
    ) as client:
        await client.patch_session_end("sess-1")

    assert calls[0] == ("PATCH", "/sessions/sess-1/end", {"partial_session": False})


@pytest.mark.asyncio
async def test_patch_session_end_threads_partial_true() -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    responses = [_ok({"partial_session": True})]

    async with BackendClient(
        "http://api.example.com",
        "tok",
        transport=_mock_transport(calls, responses),
    ) as client:
        await client.patch_session_end("sess-1", SessionEndPayload(partial_session=True))

    assert calls[0][2] == {"partial_session": True}


@pytest.mark.asyncio
async def test_authorization_header_attached_on_every_call() -> None:
    captured: list[str] = []

    def _route(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("Authorization") or "")
        return _ok({})

    async with BackendClient(
        "http://api.example.com",
        "my-token-abc",
        transport=httpx.MockTransport(_route),
    ) as client:
        await client.patch_session_end("sess-1")
        await client.post_shot("sess-1", ShotPayload(monotonic_seq=0, device_clock_ns=1))

    assert captured == ["Bearer my-token-abc", "Bearer my-token-abc"]


@pytest.mark.asyncio
async def test_4xx_raises_backend_error_with_detail() -> None:
    """4xx responses surface as BackendError with the parsed body so
    Temporal retry policy can branch on status code + the caller can
    inspect the validation detail."""

    def _route(_: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": [{"loc": ["body", "monotonic_seq"]}]})

    async with BackendClient(
        "http://api.example.com",
        "tok",
        transport=httpx.MockTransport(_route),
    ) as client:
        with pytest.raises(BackendError) as exc:
            await client.post_shot("sess-1", ShotPayload(monotonic_seq=-1, device_clock_ns=1))

    assert exc.value.status_code == 422
    assert isinstance(exc.value.detail, dict)
    assert exc.value.detail.get("detail")  # FastAPI's validation envelope


@pytest.mark.asyncio
async def test_5xx_also_raises_backend_error() -> None:
    """5xx is retryable (Temporal policy will retry); the client just
    surfaces it as a typed BackendError."""

    def _route(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream unavailable")

    async with BackendClient(
        "http://api.example.com",
        "tok",
        transport=httpx.MockTransport(_route),
    ) as client:
        with pytest.raises(BackendError) as exc:
            await client.patch_session_end("sess-1")

    assert exc.value.status_code == 503
    # No JSON body — detail falls back to the raw text.
    assert exc.value.detail == "upstream unavailable"
