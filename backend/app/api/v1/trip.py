"""POST /trip/search and POST /trip/ai-parse (docs/api-spec.yaml)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.session import require_session
from app.parsing.factory import get_parse_service
from app.parsing.models import AiParseRequest, AiParseResponse
from app.parsing.service import TripParseService
from app.trips.factory import get_trip_service
from app.trips.models import TripSearchRequest, TripSearchResponse
from app.trips.service import TripSearchError, TripSearchService

router = APIRouter()


@router.post("/trip/search", response_model=TripSearchResponse)
def search_trips(
    body: TripSearchRequest,
    _session: Annotated[str, Depends(require_session)],
    service: Annotated[TripSearchService, Depends(get_trip_service)],
) -> TripSearchResponse:
    try:
        return service.search(body, now=datetime.now(UTC))
    except TripSearchError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("/trip/ai-parse", response_model=AiParseResponse)
def ai_parse_trip(
    body: AiParseRequest,
    _session: Annotated[str, Depends(require_session)],
    service: Annotated[TripParseService, Depends(get_parse_service)],
) -> AiParseResponse:
    """Plain words -> a draft search the user confirms. Never runs the search itself (D-11)."""
    return service.parse(body.text, now=datetime.now(UTC))
