"""Liveness and version endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from ..config import get_settings
from ..schemas.tenancy import HealthOut, VersionOut

router = APIRouter(tags=["meta"])


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/version", response_model=VersionOut)
async def version() -> VersionOut:
    s = get_settings()
    return VersionOut(version=s.version, git_sha=s.git_sha, env=s.env)
