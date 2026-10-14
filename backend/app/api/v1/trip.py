"""POST /trip/search (docs/api-spec.yaml)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.session import require_session
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
