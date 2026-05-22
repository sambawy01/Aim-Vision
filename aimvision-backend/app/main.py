"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import get_settings
from .db import dispose_engines, get_app_engine, init_engines
from .middleware.audit import AuditMiddleware
from .middleware.tenant_context import TenantContextMiddleware
from .routers import (
    active_learning,
    athletes,
    auth,
    cohorts,
    consent,
    drills,
    federation,
    health,
    orgs,
    session,
)
from .services.drills import ensure_drills_seeded

logger = logging.getLogger("aimvision")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_engines()
    logger.info("aimvision-backend %s starting in %s", __version__, get_settings().env)
    # Idempotently seed the global drill catalog so it's present whether
    # the schema came from migrations (prod) or create_all (tests).
    inserted = await ensure_drills_seeded(get_app_engine())
    if inserted:
        logger.info("seeded %d drills into the catalog", inserted)
    try:
        yield
    finally:
        await dispose_engines()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AIMVISION Backend",
        version=__version__,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["x-request-id"],
    )
    app.add_middleware(AuditMiddleware, exclude_paths=("/health", "/version", "/openapi.json"))
    app.add_middleware(TenantContextMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(consent.router)
    app.include_router(athletes.router)
    app.include_router(cohorts.router)
    app.include_router(drills.router)
    app.include_router(orgs.router)
    app.include_router(session.router)
    app.include_router(active_learning.router)
    app.include_router(federation.router)

    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.detail,
                "request_id": getattr(request.state, "request_id", None),
            },
            headers=getattr(exc, "headers", None) or {},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "details": exc.errors(),
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    return app


app = create_app()
