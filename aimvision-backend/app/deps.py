"""FastAPI dependencies: principal extraction, tenant-bound DB session."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from .db import tenant_session
from .services.auth import Principal


async def current_principal(request: Request) -> Principal:
    principal: Principal | None = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


async def db_session(
    principal: Principal = Depends(current_principal),
) -> AsyncIterator[AsyncSession]:
    async with tenant_session(principal.tenant_id) as session:
        yield session


async def db_session_anon() -> AsyncIterator[AsyncSession]:
    """For pre-auth endpoints (signup/login). No principal => no RLS scope."""
    async with tenant_session(None) as session:
        yield session
