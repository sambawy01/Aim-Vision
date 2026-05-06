"""Shared pytest fixtures: in-memory SQLite engine + async test client."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

# Force a deterministic SQLite URL before app modules import.
os.environ.setdefault("AIMVISION_DATABASE_URL", "sqlite+aiosqlite:///./_aimvision_test.db")
os.environ.setdefault("AIMVISION_AUDIT_DATABASE_URL", "sqlite+aiosqlite:///./_aimvision_test.db")
os.environ.setdefault("AIMVISION_JWT_SECRET", "test-secret-test-secret-test-secret-32")
os.environ.setdefault("AIMVISION_ENV", "test")

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app import config
from app.db import dispose_engines, get_app_engine, init_engines
from app.main import create_app
from app.models import Base


@pytest_asyncio.fixture(scope="function")
async def db_schema() -> AsyncIterator[None]:
    """Build a fresh schema for each test."""
    config.get_settings.cache_clear()
    # Reset engines so a fresh DB file is in play.
    await dispose_engines()
    init_engines()
    engine = get_app_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await dispose_engines()


@pytest_asyncio.fixture
async def client(db_schema: None) -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac


@pytest.fixture
def has_postgres() -> bool:
    return os.environ.get("AIMVISION_TEST_POSTGRES_URL") is not None
