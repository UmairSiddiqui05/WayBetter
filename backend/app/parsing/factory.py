"""Builds the trip-parse service. The only place parser and geocoder adapters are chosen (N-04)."""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from app.parsing.places import PlaceResolver
from app.parsing.rules import RulesParser
from app.parsing.service import TripParseService
from app.regions import get_region_config
from app.regions.loader import resolve_region_path
from app.trips.corridor import load_corridor


@lru_cache(maxsize=1)
def get_parse_service() -> TripParseService:
    region = get_region_config()
    corridor = load_corridor(
        resolve_region_path(f"data/regions/{region.region_id}-demo-corridor.yaml")
    )
    rules = RulesParser()
    return TripParseService(
        parser=rules,
        fallback=rules,
        resolver=PlaceResolver(corridor),
        corridor=corridor,
        timezone=ZoneInfo(region.timezone),
    )
