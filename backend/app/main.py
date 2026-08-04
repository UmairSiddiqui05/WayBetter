"""FastAPI application factory.

The OpenAPI metadata below mirrors docs/api-spec.yaml (`info` block and the
`/api/v1` server prefix). Once FastAPI generates the authoritative spec, that
file stays the contract until it is version-bumped with a PROGRESS.md entry
(CLAUDE.md document precedence).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health
from app.api.v1 import api_router
from app.cache import close_redis
from app.config import API_V1_PREFIX, Settings, get_settings
from app.db import dispose_engine
from app.logging import configure_logging

API_TITLE = "WayBetter API"
API_DESCRIPTION = (
    "Park-and-ride decision engine. All routing, scoring, labeling, and explanation "
    "logic is server-side; clients render these payloads without recomputation."
)

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log.info(
        "api_startup",
        version=__version__,
        environment=settings.environment.value,
        region_config_path=settings.region_config_path,
    )
    try:
        yield
    finally:
        await dispose_engine()
        await close_redis()
        log.info("api_shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title=API_TITLE,
        version=__version__,
        description=API_DESCRIPTION,
        openapi_url=f"{API_V1_PREFIX}/openapi.json",
        docs_url=f"{API_V1_PREFIX}/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Session-Token"],
        )

    # Ops endpoints at the root, deliberately outside the versioned contract.
    app.include_router(health.router)
    # Contract endpoints (docs/api-spec.yaml). Empty until A3 lands.
    app.include_router(api_router, prefix=API_V1_PREFIX)

    return app


app = create_app()
