"""GET / — serves the demo page with the corridor presets and data sources injected server-side.

The page is a renderer only (N-01): it posts to /api/v1/trip/search and draws what comes
back. Presets and the data-source list live in data (the corridor file, the price files, the
feed metadata), so they are injected here rather than hard-coded in the HTML or exposed through
a new, uncontracted API path.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.pricing import load_pricing_data
from app.pricing.models import BarrierToll, CrossingToll, Sourced, TicketToll, ZoneToll
from app.regions import get_region_config
from app.regions.loader import resolve_region_path
from app.trips.corridor import Corridor
from app.trips.factory import get_trip_service
from app.trips.service import TripSearchService

router = APIRouter(include_in_schema=False)
TEMPLATE = Path(__file__).with_name("index.html")
STATIC_DIR = Path(__file__).with_name("static")
"""Vendored Leaflet (BSD-2), Public Sans (OFL), a Lucide icon subset (ISC) and a Natural Earth
outline basemap, so the page works offline."""


def _next_weekday_morning(now: datetime) -> datetime:
    day = now + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day.replace(hour=7, minute=0, second=0, microsecond=0)


def _source_row(category: str, name: str, item: Sourced) -> dict[str, Any]:
    url = item.source.url
    return {
        "category": category,
        "name": name,
        "source": item.source.name or (urlparse(url).netloc if url else None),
        "url": url,
        "retrieved": item.source.retrieved.isoformat(),
        "status": item.status.value,
        "human_verified": item.human_verified,
    }


def _feed_row(feed_id: str) -> dict[str, Any] | None:
    """The timetable the transit provider reads, from the metadata written at download time."""
    path = resolve_region_path(f"data/gtfs/{feed_id}.meta.json")
    if not path.exists():
        return None
    meta = json.loads(path.read_text(encoding="utf-8"))
    return {
        "category": "Train timetable (GTFS)",
        "name": meta.get("agency_name") or feed_id,
        "source": f"GTFS download; license: {meta.get('license_name') or 'unknown'}",
        "url": meta.get("source_url"),
        "retrieved": str(meta.get("retrieved_at", ""))[:10] or None,
        "status": "scheduled",  # a published timetable, by definition of GTFS static
        "human_verified": False,
    }


@lru_cache(maxsize=1)
def _data_sources_for(corridor: Corridor) -> tuple[dict[str, Any], ...]:
    """Every sourced fact the cost engine can apply: what, where from, when, and its status."""
    pricing = load_pricing_data(get_region_config())
    rows: list[dict[str, Any]] = []
    feed = _feed_row(corridor.transit_feed)
    if feed:
        rows.append(feed)
    rows += [_source_row("Rail fares", f.agency, f) for f in pricing.rail_fares]
    rows += [_source_row("Subway fare", f.agency, f) for f in pricing.flat_fares]
    tolls: list[TicketToll | BarrierToll | CrossingToll | ZoneToll] = [
        *pricing.ticket_tolls,
        *pricing.barrier_tolls,
        *pricing.crossing_tolls,
        *pricing.zone_tolls,
    ]
    rows += [_source_row("Tolls", toll.operator, toll) for toll in tolls]
    rows += [
        _source_row("Station parking", lot.name, lot)
        for group in pricing.parking_lots
        for lot in group.lots
    ]
    rows += [
        _source_row("Destination parking", area.name, area)
        for group in pricing.destination_parking
        for area in group.areas
    ]
    for vehicle in pricing.vehicle_defaults:
        rows.append(_source_row("Gas price", "Regular gasoline", vehicle.gasoline))
        rows.append(_source_row("Fuel economy", "Average new car", vehicle.fuel_economy))
    for factors in pricing.emission_factors:
        rows.append(_source_row("CO2 factor", "Gasoline, per gallon", factors.gasoline))
        rows += [
            _source_row("CO2 factor", f"{', '.join(f.modes)}, per passenger-mile", f)
            for f in factors.transit
        ]
    rows.append(_source_row("Working days", "Commute days per year", corridor.commute))
    return tuple(rows)


def _vehicle_defaults() -> dict[str, float] | None:
    """The data-file averages the server uses when the user leaves Settings blank (placeholders
    only; the page never computes with them)."""
    pricing = load_pricing_data(get_region_config())
    if not pricing.vehicle_defaults:
        return None
    vehicle = pricing.vehicle_defaults[0]
    return {"mpg": vehicle.fuel_economy.mpg, "usd_per_gallon": vehicle.gasoline.usd_per_gallon}


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
        "default_return_time": corridor.commute.default_return_time,
        "vehicle_defaults": _vehicle_defaults(),
        "data_sources": list(_data_sources_for(corridor)),
    }
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__PRESETS__*/null", json.dumps(presets).replace("</", "<\\/")
    )
    return HTMLResponse(html)
