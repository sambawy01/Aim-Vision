"""Active learning queue API — Sprint 6 EPIC 6.5.

Endpoints:

  POST   /active-learning/items            enqueue (inference pipeline)
  GET    /active-learning/items            list, filterable by status
  POST   /active-learning/items/{id}/claim claim for labelling
  POST   /active-learning/items/{id}/label submit labels
  POST   /active-learning/items/{id}/discard

Tenant scoping is enforced two ways: every row carries `tenant_id` set
from the request principal, and Postgres RLS (added in the migration)
filters every read. The router also adds an app-layer assertion for
defense in depth — the SQLite-backed test harness exercises that path.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import current_principal, db_session
from ..models.active_learning import (
    ActiveLearningItem,
    ActiveLearningStatus,
)
from ..schemas.active_learning import (
    ActiveLearningItemIn,
    ActiveLearningItemOut,
    ActiveLearningLabelIn,
)
from ..services.auth import Principal
from ..services.authz import require_role

router = APIRouter(prefix="/active-learning", tags=["active-learning"])


async def _load_item(
    item_id: str, principal: Principal, session: AsyncSession
) -> ActiveLearningItem:
    item = await session.get(ActiveLearningItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="active learning item not found")
    if item.tenant_id != principal.tenant_id:
        # App-layer assertion. RLS would prevent the row from being
        # visible at all on Postgres, but the SQLite test harness needs
        # this explicit check.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="active learning item not found")
    return item


@router.post(
    "/items",
    response_model=ActiveLearningItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def enqueue_item(
    payload: ActiveLearningItemIn,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
) -> ActiveLearningItemOut:
    item = ActiveLearningItem(
        tenant_id=principal.tenant_id,
        session_id=payload.session_id,
        shot_id=payload.shot_id,
        model_name=payload.model_name,
        model_version=payload.model_version,
        prediction=payload.prediction,
        confidence=payload.confidence,
        uncertainty_signal=payload.uncertainty_signal,
        priority=payload.priority,
        status=ActiveLearningStatus.pending,
    )
    session.add(item)
    await session.flush()
    return ActiveLearningItemOut.model_validate(item)


@router.get("/items", response_model=list[ActiveLearningItemOut])
async def list_items(
    status_filter: ActiveLearningStatus = Query(
        default=ActiveLearningStatus.pending, alias="status"
    ),
    limit: int = Query(default=20, ge=1, le=200),
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
) -> list[ActiveLearningItemOut]:
    # Tenant filter is enforced both by RLS (Postgres) and explicitly here
    # so the SQLite test path is also safe.
    stmt = (
        select(ActiveLearningItem)
        .where(
            ActiveLearningItem.tenant_id == principal.tenant_id,
            ActiveLearningItem.status == status_filter,
        )
        .order_by(
            ActiveLearningItem.priority.desc(),
            ActiveLearningItem.created_at.asc(),
        )
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [ActiveLearningItemOut.model_validate(r) for r in rows]


@router.post("/items/{item_id}/claim", response_model=ActiveLearningItemOut)
async def claim_item(
    item_id: str,
    # Only coaches and above may claim items for labelling. Athletes can
    # see their own session metadata but they are not annotators.
    principal: Principal = Depends(require_role("coach")),
    session: AsyncSession = Depends(db_session),
) -> ActiveLearningItemOut:
    item = await _load_item(item_id, principal, session)
    if item.status != ActiveLearningStatus.pending:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"item is {item.status.value}, only pending items can be claimed",
        )
    item.status = ActiveLearningStatus.claimed
    item.annotator_user_id = principal.user_id
    item.claimed_at = datetime.now(UTC)
    await session.flush()
    return ActiveLearningItemOut.model_validate(item)


@router.post("/items/{item_id}/label", response_model=ActiveLearningItemOut)
async def label_item(
    item_id: str,
    payload: ActiveLearningLabelIn,
    principal: Principal = Depends(require_role("coach")),
    session: AsyncSession = Depends(db_session),
) -> ActiveLearningItemOut:
    item = await _load_item(item_id, principal, session)
    if item.status != ActiveLearningStatus.claimed:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"item is {item.status.value}, claim before labelling",
        )
    if item.annotator_user_id != principal.user_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="only the annotator who claimed this item may label it",
        )
    item.status = ActiveLearningStatus.labelled
    item.labels = payload.labels
    item.annotator_note = payload.annotator_note
    item.labelled_at = datetime.now(UTC)
    await session.flush()
    return ActiveLearningItemOut.model_validate(item)


@router.post("/items/{item_id}/discard", response_model=ActiveLearningItemOut)
async def discard_item(
    item_id: str,
    principal: Principal = Depends(current_principal),
    session: AsyncSession = Depends(db_session),
) -> ActiveLearningItemOut:
    item = await _load_item(item_id, principal, session)
    if item.status == ActiveLearningStatus.labelled:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="labelled items cannot be discarded; data is already in the training set",
        )
    item.status = ActiveLearningStatus.discarded
    await session.flush()
    return ActiveLearningItemOut.model_validate(item)
