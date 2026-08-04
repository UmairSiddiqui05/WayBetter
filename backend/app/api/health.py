"""Ops health endpoints.

These live at the root, *outside* `/api/v1`, and are excluded from the generated
OpenAPI document. Reason: docs/api-spec.yaml is the API contract and does not
define them, so keeping them off the versioned surface lets the generated schema
stay an exact subset of the contract (checked by tests/test_openapi_parity.py).
Upstream provider health has its own contract endpoint, `/providers/status`,
which A3 owns.

- GET /healthz — liveness. Answers "is the process up?" and touches nothing else,
  so a dead database can never cause a restart loop.
- GET /readyz  — readiness. Answers "can this process serve traffic?" by probing
  Postgres/PostGIS and Redis. 503 when a required component is down.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status

from app import __version__
from app.config import Settings, get_settings
from app.health import check_readiness

router = APIRouter(tags=["ops"], include_in_schema=False)

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/healthz")
async def healthz(settings: SettingsDep) -> dict[str, str]:
    """Liveness: no dependency checks by design."""
    return {
        "status": "ok",
        "service": "waybetter-api",
        "version": __version__,
        "environment": settings.environment.value,
    }


@router.get("/readyz")
async def readyz(settings: SettingsDep, response: Response) -> dict[str, Any]:
    """Readiness: Postgres (with PostGIS) and Redis must be reachable."""
    report = await check_readiness(settings)
    if not report.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return report.as_dict()
