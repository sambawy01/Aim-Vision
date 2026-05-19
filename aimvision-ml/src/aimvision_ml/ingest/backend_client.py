"""Typed async HTTP client for the AIMVISION backend ingest surface.

Wraps the endpoints landed in backend PRs #53-#63:

  PATCH /sessions/{sid}/recording/{rid}/alignment
  POST  /sessions/{sid}/recording/{rid}/calibration
  POST  /sessions/{sid}/shots
  POST  /sessions/{sid}/shots/{shot_id}/events
  PATCH /sessions/{sid}/end

Each method takes a typed payload, serialises the snake_case wire
shape, and returns the response body parsed into a plain dict (the
backend OpenAPI is the source of truth; we deliberately don't
re-derive Pydantic models here to avoid a hard ML→backend coupling).

# Why a class, not module-level functions

A single `BackendClient(base_url, token)` instance carries the auth
context + the underlying httpx.AsyncClient. The Temporal workflow
activities each open one and use it for one workflow run; the
async context manager guards connection pool cleanup. Per ADR-0007
activities are idempotent — that's the responsibility of the caller
+ the backend's idempotent endpoints, not this client.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any

import httpx


class BackendError(RuntimeError):
    """Raised when the backend returns a non-2xx response.

    Carries the status code + response body so callers can branch on
    e.g. 404 vs 422. The Temporal retry policy uses the status code
    to decide whether to retry (5xx + 429 yes, 4xx no).
    """

    def __init__(self, status_code: int, detail: Any) -> None:
        super().__init__(f"backend returned HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class AlignmentPayload:
    session_clock_offset_ns: int
    session_clock_offset_confidence: float


@dataclass(frozen=True, slots=True)
class CalibrationPayload:
    """Mirrors backend's CameraCalibrationIn (multi-camera-sync-spec §4.5)."""

    intrinsics_k_json: list[list[float]]
    distortion_coeffs_json: list[float]
    extrinsics_r_json: list[list[float]]
    extrinsics_t_json: list[float]
    reprojection_error_px_p95: float
    charuco_frames_used: int
    calibration_ts_ns: int


@dataclass(frozen=True, slots=True)
class ShotPayload:
    monotonic_seq: int
    device_clock_ns: int
    shot_kind: str = "single"


@dataclass(frozen=True, slots=True)
class ShotEventPayload:
    event_kind: str
    monotonic_seq: int
    payload: dict[str, Any]
    produced_at: datetime


@dataclass(frozen=True, slots=True)
class SessionEndPayload:
    partial_session: bool = False


class BackendClient:
    """Async HTTP client for the post-session ingest endpoints.

    Use as an async context manager:

        async with BackendClient(base_url, token) as client:
            await client.patch_alignment(sid, rid, AlignmentPayload(...))
            await client.post_calibration(sid, rid, CalibrationPayload(...))
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # `transport` is exposed so tests can plug in
        # `httpx.MockTransport` without spinning a real backend up.
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_s,
            transport=transport,
        )

    async def __aenter__(self) -> BackendClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._client.aclose()

    @staticmethod
    def _raise_if_error(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        try:
            detail = resp.json()
        except ValueError:
            detail = resp.text
        raise BackendError(resp.status_code, detail)

    async def patch_alignment(
        self, session_id: str, recording_id: str, payload: AlignmentPayload
    ) -> dict[str, Any]:
        """Set the audio-xcorr alignment fields on a recording.

        Producer is `aimvision_ml.inference.audio_xcorr.align_camera_pair`.
        Backend PR #53.
        """
        resp = await self._client.patch(
            f"/sessions/{session_id}/recording/{recording_id}/alignment",
            json={
                "session_clock_offset_ns": payload.session_clock_offset_ns,
                "session_clock_offset_confidence": payload.session_clock_offset_confidence,
            },
        )
        self._raise_if_error(resp)
        return dict(resp.json())

    async def post_calibration(
        self, session_id: str, recording_id: str, payload: CalibrationPayload
    ) -> dict[str, Any]:
        """Persist a new ChArUco-derived calibration row for a recording.

        Producer is the bundle-adjustment output from
        `aimvision_ml.inference.camera_calibration.refine_calibration`.
        Backend PR #57.
        """
        resp = await self._client.post(
            f"/sessions/{session_id}/recording/{recording_id}/calibration",
            json={
                "intrinsics_k_json": payload.intrinsics_k_json,
                "distortion_coeffs_json": payload.distortion_coeffs_json,
                "extrinsics_r_json": payload.extrinsics_r_json,
                "extrinsics_t_json": payload.extrinsics_t_json,
                "reprojection_error_px_p95": payload.reprojection_error_px_p95,
                "charuco_frames_used": payload.charuco_frames_used,
                "calibration_ts_ns": payload.calibration_ts_ns,
            },
        )
        self._raise_if_error(resp)
        return dict(resp.json())

    async def post_shot(self, session_id: str, payload: ShotPayload) -> dict[str, Any]:
        """Ingest a detected shot into the session's append-only stream.

        Producer is `aimvision_ml.inference.audio_shot`. Backend PR #59.
        Idempotent on (session_id, monotonic_seq) — safe to retry.
        """
        resp = await self._client.post(
            f"/sessions/{session_id}/shots",
            json={
                "monotonic_seq": payload.monotonic_seq,
                "device_clock_ns": payload.device_clock_ns,
                "shot_kind": payload.shot_kind,
            },
        )
        self._raise_if_error(resp)
        return dict(resp.json())

    async def post_shot_event(
        self, session_id: str, shot_id: str, payload: ShotEventPayload
    ) -> dict[str, Any]:
        """Append a namespaced event to a shot's append-only stream.

        Producers include the diagnostic head, pose pipeline, coach UI.
        Backend PR #60. Idempotent on (shot_id, event_kind, monotonic_seq).
        """
        resp = await self._client.post(
            f"/sessions/{session_id}/shots/{shot_id}/events",
            json={
                "event_kind": payload.event_kind,
                "monotonic_seq": payload.monotonic_seq,
                "payload": payload.payload,
                # httpx serialises datetimes via ISO-8601; keep that
                # explicit so the snake_case wire shape is unambiguous.
                "produced_at": payload.produced_at.isoformat(),
            },
        )
        self._raise_if_error(resp)
        return dict(resp.json())

    async def patch_session_end(
        self, session_id: str, payload: SessionEndPayload | None = None
    ) -> dict[str, Any]:
        """Close the session lifecycle. Backend PR #62.

        `partial_session` overwrites on every call (the post-session
        worker can flip it on after the fact when degraded-mode
        handlers trigger). `ended_at` is set on first call and
        preserved thereafter.
        """
        body = {
            "partial_session": (payload.partial_session if payload is not None else False),
        }
        resp = await self._client.patch(
            f"/sessions/{session_id}/end",
            json=body,
        )
        self._raise_if_error(resp)
        return dict(resp.json())
