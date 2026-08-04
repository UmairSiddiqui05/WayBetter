"""Readiness probes for the containers Compose owns.

Scope note: these are *infrastructure* probes (can the process reach its
datastores?), deliberately not the `/providers/status` contract endpoint, which
reports upstream provider health through the provider interfaces and belongs to
A3/A4 (N-04). Nothing here is user-facing, so nothing here carries provenance.

Gating rule: Postgres (with PostGIS) and Redis gate readiness. OTP does not —
it is a placeholder until A2 builds and ships a graph bundle (N-08), so its
status is reported for operators without failing the probe.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

import httpx
import structlog
from sqlalchemy import text

from app.cache import get_redis
from app.config import Settings
from app.db import get_engine

log = structlog.get_logger(__name__)

POSTGIS_VERSION_SQL = text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    name: str
    status: HealthStatus
    detail: str | None = None
    required: bool = True


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    components: tuple[ComponentHealth, ...]

    @property
    def ready(self) -> bool:
        return all(c.status is HealthStatus.OK for c in self.components if c.required)

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "ready" if self.ready else "not_ready",
            "components": {
                c.name: {"status": c.status.value, "detail": c.detail, "required": c.required}
                for c in self.components
            },
        }


async def check_postgres(settings: Settings) -> ComponentHealth:
    """Connectivity plus a PostGIS availability check — PostGIS is not optional (F-07)."""
    try:
        async with asyncio.timeout(settings.probe_timeout_seconds):
            async with get_engine().connect() as conn:
                await conn.execute(text("SELECT 1"))
                result = await conn.execute(POSTGIS_VERSION_SQL)
                postgis_version = result.scalar_one_or_none()
    except Exception as exc:
        # A probe reports failure; it never raises into the request path.
        log.warning("postgres_probe_failed", error=type(exc).__name__)
        return ComponentHealth("postgres", HealthStatus.DOWN, detail=type(exc).__name__)

    if postgis_version is None:
        return ComponentHealth(
            "postgres", HealthStatus.DEGRADED, detail="postgis extension not installed"
        )
    return ComponentHealth("postgres", HealthStatus.OK, detail=f"postgis {postgis_version}")


async def check_redis(settings: Settings) -> ComponentHealth:
    try:
        async with asyncio.timeout(settings.probe_timeout_seconds):
            await get_redis().ping()
    except Exception as exc:
        log.warning("redis_probe_failed", error=type(exc).__name__)
        return ComponentHealth("redis", HealthStatus.DOWN, detail=type(exc).__name__)
    return ComponentHealth("redis", HealthStatus.OK)


async def check_otp(settings: Settings) -> ComponentHealth:
    """Non-gating: OTP has no graph until A2 produces a versioned bundle."""
    url = f"{settings.otp_base_url.rstrip('/')}/actuators/health"
    try:
        async with httpx.AsyncClient(timeout=settings.probe_timeout_seconds) as client:
            response = await client.get(url)
    except Exception as exc:
        log.info("otp_probe_failed", error=type(exc).__name__)
        return ComponentHealth("otp", HealthStatus.DOWN, detail=type(exc).__name__, required=False)

    if response.is_success:
        return ComponentHealth("otp", HealthStatus.OK, required=False)
    return ComponentHealth(
        "otp", HealthStatus.DEGRADED, detail=f"HTTP {response.status_code}", required=False
    )


async def check_readiness(settings: Settings) -> ReadinessReport:
    postgres, redis_health, otp = await asyncio.gather(
        check_postgres(settings), check_redis(settings), check_otp(settings)
    )
    return ReadinessReport(components=(postgres, redis_health, otp))
