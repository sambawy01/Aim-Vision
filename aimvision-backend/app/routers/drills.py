"""Drills endpoint — the global coaching-drill catalog.

`GET /drills` returns the canonical drill library that the LLM
coaching note's `recommended_drills` reference (the verifier rejects
any drill id not in this catalog). The catalog is global, not
tenant-scoped, so this is open to any authenticated principal; an
optional `discipline` filter narrows it (a "trap" query returns
trap-specific drills plus the `all`-discipline ones).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import current_principal, db_session
from ..models.drill import Drill
from ..schemas.drills import DrillOut
from ..services.auth import Principal

router = APIRouter(prefix="/drills", tags=["drills"])


@router.get("", response_model=list[DrillOut])
async def list_drills(
    discipline: str | None = Query(
        default=None,
        description='Filter to a discipline (e.g. "skeet"); "all" drills always included.',
    ),
    _: Principal = Depends(current_principal),
    db: AsyncSession = Depends(db_session),
) -> list[DrillOut]:
    stmt = select(Drill).order_by(Drill.id.asc())
    if discipline is not None:
        # Discipline-specific drills + the universally-applicable ones.
        stmt = stmt.where(Drill.discipline.in_([discipline, "all"]))
    rows = (await db.execute(stmt)).scalars().all()
    return [DrillOut.model_validate(r) for r in rows]
