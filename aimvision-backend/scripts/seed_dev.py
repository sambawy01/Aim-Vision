"""Seed a local dev database with a coach + athletes you can actually use.

The login endpoint mints the token for a user's highest-privilege membership,
so to exercise the coach/admin web UI (federation dashboard, right-to-erasure,
new-session form) you need a real coach `Membership` plus athletes to pick
from. Signup only ever creates a solo athlete tenancy, so this script layers a
club, a coach, and a handful of athletes (all in the same club tenant) on top.

Usage (SQLite, no Postgres needed):

    cd aimvision-backend
    AIMVISION_DATABASE_URL="sqlite+aiosqlite:///./_aimvision_dev.db" \
    AIMVISION_AUDIT_DATABASE_URL="sqlite+aiosqlite:///./_aimvision_dev.db" \
      .venv/bin/python -m scripts.seed_dev

Then start the API and log in with the printed credentials.
Idempotent: re-running refreshes the coach password and leaves one membership
of each role per user.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.models  # noqa: F401  (register all models for create_all)
from app.db import dispose_engines, get_app_engine, init_engines
from app.models.base import Base
from app.models.tenancy import Account, Membership, Org, OrgKind, Role, User
from app.services.auth import hash_password

COACH_EMAIL = "coach@example.com"
COACH_PASSWORD = "demopassword123"  # local dev credential, not a secret
CLUB_TENANT = "org:democlub"
CLUB_ORG_ID = "org-democlub"

# (email, display_name) — athletes the coach can pick in the new-session form.
DEMO_ATHLETES: list[tuple[str, str]] = [
    ("anna.athlete@example.com", "Anna Athlete"),
    ("bilal.athlete@example.com", "Bilal Athlete"),
    ("carmen.athlete@example.com", "Carmen Athlete"),
]


async def _ensure_user(s: AsyncSession, email: str, display_name: str) -> User:
    """Get-or-create a user (with its account + implicit solo org)."""
    user = (await s.execute(select(User).where(User.email == email))).scalars().first()
    if user is not None:
        return user
    account = Account(name=display_name)
    s.add(account)
    await s.flush()
    user = User(
        account_id=account.id,
        email=email,
        password_hash=hash_password(COACH_PASSWORD),
        display_name=display_name,
    )
    s.add(user)
    await s.flush()
    s.add(Org(kind=OrgKind.solo, name=f"{display_name} (solo)", tenant_id=f"solo:{user.id}"))
    return user


async def _ensure_membership(s: AsyncSession, *, user: User, org_id: str, role: Role) -> None:
    existing = (
        (
            await s.execute(
                select(Membership).where(
                    Membership.user_id == user.id,
                    Membership.org_id == org_id,
                    Membership.role == role,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        s.add(
            Membership(
                user_id=user.id,
                org_id=org_id,
                role=role,
                tenant_id=CLUB_TENANT,
                is_active=True,
            )
        )


async def _seed() -> None:
    init_engines()
    engine = get_app_engine()
    # Ensure schema exists (alembic 0003 is Postgres-only RLS, so on SQLite we
    # build from the ORM metadata instead).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s, s.begin():
        # Demo club.
        club = (await s.execute(select(Org).where(Org.id == CLUB_ORG_ID))).scalars().first()
        if club is None:
            s.add(Org(id=CLUB_ORG_ID, kind=OrgKind.club, name="Demo Club", tenant_id=CLUB_TENANT))

        # Coach (refresh password on re-run so the printed login always works).
        coach = await _ensure_user(s, COACH_EMAIL, "Demo Coach")
        coach.password_hash = hash_password(COACH_PASSWORD)
        await _ensure_membership(s, user=coach, org_id=CLUB_ORG_ID, role=Role.coach)

        # Athletes the coach can pick for a new session.
        for email, name in DEMO_ATHLETES:
            athlete = await _ensure_user(s, email, name)
            await _ensure_membership(s, user=athlete, org_id=CLUB_ORG_ID, role=Role.athlete)

    await dispose_engines()
    print("Seeded dev data:")
    print(f"  coach login: {COACH_EMAIL} / {COACH_PASSWORD}")
    print(f"  tenant:      {CLUB_TENANT} (Demo Club)")
    print(f"  athletes:    {', '.join(name for _, name in DEMO_ATHLETES)}")


if __name__ == "__main__":
    asyncio.run(_seed())
