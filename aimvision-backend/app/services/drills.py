"""Idempotent drill-catalog seeding.

Run on app startup (lifespan) so the global drill catalog is present
regardless of whether the schema was built by migrations (prod) or
`Base.metadata.create_all` (tests). Inserts any catalog rows missing
from the `drills` table; existing rows are left untouched (the
catalog is a controlled reference set, not user data).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.data.drills import DRILL_CATALOG
from app.models.drill import Drill


async def ensure_drills_seeded(engine: AsyncEngine) -> int:
    """Insert any missing catalog drills. Returns the number inserted."""
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session, session.begin():
        existing = set((await session.execute(select(Drill.id))).scalars().all())
        inserted = 0
        for seed in DRILL_CATALOG:
            if seed["id"] in existing:
                continue
            session.add(
                Drill(
                    id=seed["id"],
                    name=seed["name"],
                    description=seed["description"],
                    discipline=seed["discipline"],
                    target_categories=list(seed["target_categories"]),
                )
            )
            inserted += 1
    return inserted
