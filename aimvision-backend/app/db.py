"""Database engines, sessions, and tenant-scoped session contexts.

Two engines exist by design (per docs/security/audit-logging-spec.md §4.4):

* `app_engine`  -- the application role; bound by RLS policies.
* `audit_engine` -- the audit_writer role; INSERT-only on audit_events.

`tenant_session(principal)` opens a session that begins a transaction and runs
``SET LOCAL app.current_principal = <principal>`` so RLS policies key off the
correct tenant. On SQLite (tests) the SET is silently skipped -- RLS is a
PostgreSQL feature; the application-layer scope filter still applies.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import Settings, get_settings

_app_engine: AsyncEngine | None = None
_audit_engine: AsyncEngine | None = None
_app_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_audit_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _make_engine(url: str) -> AsyncEngine:
    # SQLite needs StaticPool semantics off the path of pool_pre_ping; default OK for tests.
    if url.startswith("sqlite"):
        return create_async_engine(url, future=True)
    return create_async_engine(url, future=True, pool_pre_ping=True, pool_size=10, max_overflow=10)


def init_engines(settings: Settings | None = None) -> None:
    global _app_engine, _audit_engine, _app_sessionmaker, _audit_sessionmaker
    s = settings or get_settings()
    if _app_engine is None:
        _app_engine = _make_engine(s.database_url)
        _app_sessionmaker = async_sessionmaker(_app_engine, expire_on_commit=False)
    if _audit_engine is None:
        _audit_engine = _make_engine(s.effective_audit_database_url)
        _audit_sessionmaker = async_sessionmaker(_audit_engine, expire_on_commit=False)


async def dispose_engines() -> None:
    global _app_engine, _audit_engine, _app_sessionmaker, _audit_sessionmaker
    if _app_engine is not None:
        await _app_engine.dispose()
    if _audit_engine is not None and _audit_engine is not _app_engine:
        await _audit_engine.dispose()
    _app_engine = None
    _audit_engine = None
    _app_sessionmaker = None
    _audit_sessionmaker = None


def get_app_engine() -> AsyncEngine:
    if _app_engine is None:
        init_engines()
    assert _app_engine is not None
    return _app_engine


def get_audit_engine() -> AsyncEngine:
    if _audit_engine is None:
        init_engines()
    assert _audit_engine is not None
    return _audit_engine


def _is_postgres_engine(engine: AsyncEngine) -> bool:
    return engine.url.get_backend_name().startswith("postgresql")


@asynccontextmanager
async def tenant_session(principal: str | None) -> AsyncIterator[AsyncSession]:
    """Yield a session bound to a transaction with `app.current_principal` set."""
    if _app_sessionmaker is None:
        init_engines()
    assert _app_sessionmaker is not None

    async with _app_sessionmaker() as session, session.begin():
        if principal is not None and _is_postgres_engine(get_app_engine()):
            # Transaction-scoped GUC; per ADR-0004 §connection pooling.
            from sqlalchemy import text

            await session.execute(
                text("SELECT set_config('app.current_principal', :p, true)"),
                {"p": principal},
            )
        yield session


@asynccontextmanager
async def system_session() -> AsyncIterator[AsyncSession]:
    """Elevated session bound to the audit-writer engine. INSERT-only on audit_events."""
    if _audit_sessionmaker is None:
        init_engines()
    assert _audit_sessionmaker is not None
    async with _audit_sessionmaker() as session, session.begin():
        yield session
