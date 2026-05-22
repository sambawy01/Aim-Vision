"""Seed a local dev database with a coach account you can actually log in as.

The login endpoint mints the token for a user's highest-privilege membership,
so to exercise the coach/admin web UI (federation dashboard, right-to-erasure)
you need a real coach `Membership`. Signup only ever creates a solo athlete
tenancy, so this script layers a club + coach membership on top.

Usage (SQLite, no Postgres needed):

    cd aimvision-backend
    AIMVISION_DATABASE_URL="sqlite+aiosqlite:///./_aimvision_dev.db" \
    AIMVISION_AUDIT_DATABASE_URL="sqlite+aiosqlite:///./_aimvision_dev.db" \
      .venv/bin/python -m scripts.seed_dev

Then start the API and log in with the printed credentials.
Idempotent: re-running updates the password and leaves one coach membership.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

import app.models  # noqa: F401  (register all models for create_all)
from app.db import dispose_engines, get_app_engine, init_engines
from app.models.base import Base
from app.models.tenancy import Account, Membership, Org, OrgKind, Role, User
from app.services.auth import hash_password

COACH_EMAIL = "coach@example.com"
COACH_PASSWORD = "demopassword123"  # local dev credential, not a secret
CLUB_TENANT = "org:democlub"
CLUB_ORG_ID = "org-democlub"


async def _seed() -> None:
    init_engines()
    engine = get_app_engine()
    # Ensure schema exists (alembic 0003 is Postgres-only RLS, so on SQLite we
    # build from the ORM metadata instead).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as s, s.begin():
        user = (await s.execute(select(User).where(User.email == COACH_EMAIL))).scalars().first()
        if user is None:
            account = Account(name="Demo Coach")
            s.add(account)
            await s.flush()
            user = User(
                account_id=account.id,
                email=COACH_EMAIL,
                password_hash=hash_password(COACH_PASSWORD),
                display_name="Demo Coach",
            )
            s.add(user)
            await s.flush()
            # Solo org the login synthesizes the implicit solo tenancy from.
            s.add(Org(kind=OrgKind.solo, name="Demo Coach (solo)", tenant_id=f"solo:{user.id}"))
        else:
            user.password_hash = hash_password(COACH_PASSWORD)

        club = (await s.execute(select(Org).where(Org.id == CLUB_ORG_ID))).scalars().first()
        if club is None:
            s.add(Org(id=CLUB_ORG_ID, kind=OrgKind.club, name="Demo Club", tenant_id=CLUB_TENANT))

        existing = (
            (
                await s.execute(
                    select(Membership).where(
                        Membership.user_id == user.id,
                        Membership.org_id == CLUB_ORG_ID,
                        Membership.role == Role.coach,
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
                    org_id=CLUB_ORG_ID,
                    role=Role.coach,
                    tenant_id=CLUB_TENANT,
                    is_active=True,
                )
            )

    await dispose_engines()
    print("Seeded coach login:")
    print(f"  email:    {COACH_EMAIL}")
    print(f"  password: {COACH_PASSWORD}")
    print(f"  tenant:   {CLUB_TENANT} (role: coach)")


if __name__ == "__main__":
    asyncio.run(_seed())
