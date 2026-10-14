"""GET / — serves the demo page with the corridor presets injected server-side.

The page is a renderer only (N-01): it posts to /api/v1/trip/search and draws what comes
back. Presets live in data (the corridor file), so they are injected here rather than
hard-coded in the HTML or exposed through a new, uncontracted API path.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.trips.factory import get_trip_service
from app.trips.service import TripSearchService

router = APIRouter(include_in_schema=False)
TEMPLATE = Path(__file__).with_name("index.html")


def _next_weekday_morning(now: datetime) -> datetime:
    day = now + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.replace(hour=7, minute=0, second=0, microsecond=0)


@router.get("/", response_class=HTMLResponse)
def demo_page(service: Annotated[TripSearchService, Depends(get_trip_service)]) -> HTMLResponse:
    corridor = service.corridor
    presets = {
        "corridor": corridor.name,
        "origins": [
            {"id": p.id, "label": p.label, "lat": p.lat, "lng": p.lng} for p in corridor.origins
        ],
        "destinations": [
            {"id": p.id, "label": p.label, "lat": p.lat, "lng": p.lng}
            for p in corridor.destinations
        ],
        "default_departure": _next_weekday_morning(datetime.now(service.timezone)).strftime(
            "%Y-%m-%dT%H:%M"
        ),
    }
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__PRESETS__*/null", json.dumps(presets).replace("</", "<\\/")
    )
    return HTMLResponse(html)
