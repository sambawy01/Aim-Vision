"""Session listing / read endpoints + Recording upload (ADR-0009 slice 2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..deps import current_principal, db_session
from ..models import CameraCalibration, Recording, RecordingSourceKind, Role
from ..models.base import new_uuid
from ..models.session import Session as SessionModel
from ..schemas.camera_calibration import CameraCalibrationIn, CameraCalibrationOut
from ..schemas.session import AlignmentIn, RecordingOut, SessionOut
from ..services.auth import Principal
from ..services.authz import require_role
from ..services.storage import Storage, get_storage

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
    limit: int = 50,
) -> list[SessionOut]:
    stmt = (
        select(SessionModel)
        .where(SessionModel.tenant_id == principal.tenant_id)
        .order_by(SessionModel.started_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    result = await session.execute(stmt)
    return [SessionOut.model_validate(row) for row in result.scalars().all()]


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(
    session_id: str,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
) -> SessionOut:
    stmt = select(SessionModel).where(
        SessionModel.id == session_id,
        SessionModel.tenant_id == principal.tenant_id,
    )
    result = await session.execute(stmt)
    row = result.scalars().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    return SessionOut.model_validate(row)


@router.get(
    "/{session_id}/recording",
    response_model=list[RecordingOut],
)
async def list_recordings(
    session_id: str,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[RecordingOut]:
    """List recordings under a session in the caller's tenant.

    Tenant scoping enforced via Session.tenant_id; a recording in
    another tenant returns an empty list (the session lookup fails
    first, 404). No role gate — any authenticated principal in the
    tenant can list, matching the pattern of GET /sessions/{id}.
    """
    parent = (
        (
            await db.execute(
                select(SessionModel).where(
                    SessionModel.id == session_id,
                    SessionModel.tenant_id == principal.tenant_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if parent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")
    rows = (
        (
            await db.execute(
                select(Recording)
                .where(Recording.session_id == session_id)
                .order_by(Recording.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [RecordingOut.model_validate(r) for r in rows]


@router.get(
    "/{session_id}/recording/{recording_id}",
    response_model=RecordingOut,
)
async def get_recording(
    session_id: str,
    recording_id: str,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(db_session),
) -> RecordingOut:
    """Single recording by id. Returns 404 on cross-tenant access or
    a session-id mismatch (the same compound where-clause as the
    PATCH alignment endpoint, for consistent error semantics)."""
    stmt = (
        select(Recording)
        .join(SessionModel, Recording.session_id == SessionModel.id)
        .where(
            Recording.id == recording_id,
            Recording.session_id == session_id,
            SessionModel.tenant_id == principal.tenant_id,
        )
    )
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="recording not found")
    return RecordingOut.model_validate(row)


@router.post(
    "/{session_id}/recording",
    response_model=RecordingOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_recording(
    session_id: str,
    file: UploadFile = File(..., description="MP4 video payload"),
    source_kind: RecordingSourceKind = Form(
        default=RecordingSourceKind.hero13,
        description="Which camera backend produced this file. Defaults to hero13.",
    ),
    duration_ms: int | None = Form(default=None, description="Optional duration hint"),
    camera_clock_offset_ms: int | None = Form(
        default=None,
        description="Camera↔server clock skew at recording start, milliseconds",
    ),
    # require_role(coach) ensures only a coach (or higher) can ingest; the
    # athlete tier can record on-device but the upload goes through
    # `claimed-by-coach`. Adjusted in future slices when athletes upload directly.
    principal: Principal = Depends(require_role(Role.coach.value)),
    db: AsyncSession = Depends(db_session),
    storage: Storage = Depends(get_storage),
) -> RecordingOut:
    """Ingest an MP4 recording for an existing session.

    Slice 2 of ADR-0009. The file is streamed to the configured storage
    backend (LocalFsStorage in V1; S3 in a later slice via the same
    Storage protocol). Recording row is created with the computed
    storage_uri, sha256, size, and the source_kind tag for downstream
    aggregation filtering.
    """
    # Verify the parent session exists in the caller's tenant. We do
    # the explicit tenant check on top of RLS so the SQLite test path
    # also enforces isolation (RLS only fires on Postgres).
    parent = (
        (
            await db.execute(
                select(SessionModel).where(
                    SessionModel.id == session_id,
                    SessionModel.tenant_id == principal.tenant_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if parent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session not found")

    recording_id = new_uuid()
    stored = await storage.store_upload(
        upload=file,
        tenant_id=principal.tenant_id,
        session_id=session_id,
        recording_id=recording_id,
        max_bytes=get_settings().max_recording_upload_bytes,
    )

    row = Recording(
        id=recording_id,
        session_id=session_id,
        storage_uri=stored.storage_uri,
        sha256=stored.sha256_hex,
        duration_ms=duration_ms,
        upload_state="uploaded",
        camera_clock_offset_ms=camera_clock_offset_ms,
        source_kind=source_kind,
        tenant_id=principal.tenant_id,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return RecordingOut.model_validate(row)


@router.patch(
    "/{session_id}/recording/{recording_id}/alignment",
    response_model=RecordingOut,
)
async def update_recording_alignment(
    session_id: str,
    recording_id: str,
    payload: AlignmentIn,
    # The Temporal worker that computes alignment runs as a coach-tier
    # service account; this is also the role a coach uses for manual
    # recalibration. Federation admin inherits via the role hierarchy.
    principal: Principal = Depends(require_role(Role.coach.value)),
    db: AsyncSession = Depends(db_session),
) -> RecordingOut:
    """Set the audio-xcorr alignment fields on a recording.

    ADR-0009 slice 4: after the post-session pipeline runs
    `aimvision_ml.inference.audio_xcorr.align_camera_pair`, the median
    offset + confidence land here. The two fields are written
    atomically per the API contract (the schema admits either or
    neither, never one without the other).

    Tenant scoping is enforced by joining recordings → sessions and
    checking the session's tenant_id matches the caller's principal.
    Postgres RLS layers on the same constraint; this explicit check
    is what makes the SQLite test path safe.
    """
    stmt = (
        select(Recording)
        .join(SessionModel, Recording.session_id == SessionModel.id)
        .where(
            Recording.id == recording_id,
            Recording.session_id == session_id,
            SessionModel.tenant_id == principal.tenant_id,
        )
    )
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="recording not found")

    row.session_clock_offset_ns = payload.session_clock_offset_ns
    row.session_clock_offset_confidence = payload.session_clock_offset_confidence
    await db.flush()
    await db.refresh(row)
    return RecordingOut.model_validate(row)


async def _recording_in_tenant_or_404(
    db: AsyncSession, principal: Principal, session_id: str, recording_id: str
) -> Recording:
    """Compound (recording_id, session_id, session.tenant_id) lookup
    used by both calibration endpoints. Mirrors the alignment PATCH
    pattern so error responses are consistent across read + write
    paths."""
    stmt = (
        select(Recording)
        .join(SessionModel, Recording.session_id == SessionModel.id)
        .where(
            Recording.id == recording_id,
            Recording.session_id == session_id,
            SessionModel.tenant_id == principal.tenant_id,
        )
    )
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="recording not found")
    return row


@router.post(
    "/{session_id}/recording/{recording_id}/calibration",
    response_model=CameraCalibrationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_recording_calibration(
    session_id: str,
    recording_id: str,
    payload: CameraCalibrationIn,
    # Calibration writes come from the post-session Temporal worker
    # (coach-tier service account) or from a coach running manual
    # recalibration; federation_admin inherits via the role hierarchy.
    principal: Principal = Depends(require_role(Role.coach.value)),
    db: AsyncSession = Depends(db_session),
) -> CameraCalibrationOut:
    """Persist a new ChArUco-derived calibration for a recording.

    Multi-camera-sync-spec.md §4.5 — multiple calibration rows per
    recording are permitted (mid-session recalibration trigger from
    §4.4). The GET endpoint returns the most recent.
    """
    await _recording_in_tenant_or_404(db, principal, session_id, recording_id)

    row = CameraCalibration(
        id=new_uuid(),
        session_id=session_id,
        recording_id=recording_id,
        tenant_id=principal.tenant_id,
        intrinsics_k_json=payload.intrinsics_k_json,
        distortion_coeffs_json=payload.distortion_coeffs_json,
        extrinsics_r_json=payload.extrinsics_r_json,
        extrinsics_t_json=payload.extrinsics_t_json,
        reprojection_error_px_p95=payload.reprojection_error_px_p95,
        charuco_frames_used=payload.charuco_frames_used,
        calibration_ts_ns=payload.calibration_ts_ns,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return CameraCalibrationOut.model_validate(row)


@router.get(
    "/{session_id}/recording/{recording_id}/calibration",
    response_model=CameraCalibrationOut,
)
async def get_recording_calibration(
    session_id: str,
    recording_id: str,
    principal: Principal = Depends(current_principal),
    db: AsyncSession = Depends(db_session),
) -> CameraCalibrationOut:
    """Return the most-recent calibration for a recording.

    Selected by `calibration_ts_ns DESC` so mid-session recalibration
    overrides the original. Returns 404 if no calibration has been
    written yet OR the recording isn't visible to the principal.
    """
    await _recording_in_tenant_or_404(db, principal, session_id, recording_id)

    stmt = (
        select(CameraCalibration)
        .where(
            CameraCalibration.recording_id == recording_id,
            CameraCalibration.session_id == session_id,
        )
        .order_by(CameraCalibration.calibration_ts_ns.desc())
        .limit(1)
    )
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="no calibration for this recording")
    return CameraCalibrationOut.model_validate(row)
