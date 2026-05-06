"""RLS-based tenancy isolation. Requires a real Postgres -- skipped on SQLite.

Set AIMVISION_TEST_POSTGRES_URL to enable, e.g.::

    AIMVISION_TEST_POSTGRES_URL=postgresql+asyncpg://aimvision:aimvision@localhost:5432/aimvision_test

CI provides this via the postgres:16 service container.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base, OrgKind
from app.models.tenancy import Org

PG_URL = os.environ.get("AIMVISION_TEST_POSTGRES_URL")

pytestmark = pytest.mark.postgres


@pytest.mark.skipif(PG_URL is None, reason="AIMVISION_TEST_POSTGRES_URL not set")
async def test_rls_isolates_two_tenants() -> None:
    assert PG_URL is not None
    engine = create_async_engine(PG_URL, future=True)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    # Fresh schema + RLS via the migration script equivalent.
    # Important: Postgres superusers bypass RLS even with FORCE; we must
    # create a NOBYPASSRLS role and SET ROLE to it for the policy to apply.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE orgs ENABLE ROW LEVEL SECURITY;"))
        await conn.execute(text("ALTER TABLE orgs FORCE ROW LEVEL SECURITY;"))
        await conn.execute(text("DROP POLICY IF EXISTS tenant_iso ON orgs;"))
        await conn.execute(
            text(
                "CREATE POLICY tenant_iso ON orgs FOR ALL "
                "USING (tenant_id = current_setting('app.current_principal', true)) "
                "WITH CHECK (tenant_id = current_setting('app.current_principal', true));"
            )
        )
        # NOBYPASSRLS role used by the application at runtime.
        await conn.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='aimvision_app') THEN "
                "CREATE ROLE aimvision_app NOBYPASSRLS NOSUPERUSER; "
                "END IF; END $$;"
            )
        )
        await conn.execute(text("GRANT ALL ON TABLE orgs TO aimvision_app;"))

    # Insert as tenant A and tenant B respectively (under aimvision_app role).
    async with sessionmaker() as session:
        async with session.begin():
            await session.execute(text("SET LOCAL ROLE aimvision_app"))
            await session.execute(text("SELECT set_config('app.current_principal', 'org:a', true)"))
            session.add(Org(kind=OrgKind.club, name="Club A", tenant_id="org:a"))
        async with session.begin():
            await session.execute(text("SET LOCAL ROLE aimvision_app"))
            await session.execute(text("SELECT set_config('app.current_principal', 'org:b', true)"))
            session.add(Org(kind=OrgKind.club, name="Club B", tenant_id="org:b"))

    # Reading as principal A must see only A.
    async with sessionmaker() as session, session.begin():
        await session.execute(text("SET LOCAL ROLE aimvision_app"))
        await session.execute(text("SELECT set_config('app.current_principal', 'org:a', true)"))
        result = await session.execute(select(Org))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].tenant_id == "org:a"

    # Reading as principal B must see only B.
    async with sessionmaker() as session, session.begin():
        await session.execute(text("SET LOCAL ROLE aimvision_app"))
        await session.execute(text("SELECT set_config('app.current_principal', 'org:b', true)"))
        result = await session.execute(select(Org))
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].tenant_id == "org:b"

    await engine.dispose()
