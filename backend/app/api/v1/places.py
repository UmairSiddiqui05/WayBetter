"""POST /places/resolve (docs/api-spec.yaml v0.4.0): one typed From/To place -> a point."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.session import require_session
from app.parsing.factory import get_parse_service
from app.parsing.models import PlaceLookupRequest, PlaceLookupResponse
from app.parsing.service import TripParseService

router = APIRouter()


@router.post("/places/resolve", response_model=PlaceLookupResponse)
def resolve_place(
    body: PlaceLookupRequest,
    _session: Annotated[str, Depends(require_session)],
    service: Annotated[TripParseService, Depends(get_parse_service)],
) -> PlaceLookupResponse:
    """Session required: the address lookup is a rate-limited outside service (N-05)."""
    return service.lookup_place(body.text, body.role)
