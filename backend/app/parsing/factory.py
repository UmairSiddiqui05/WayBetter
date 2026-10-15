"""Builds the trip-parse service. The only place parser and geocoder adapters are chosen (N-04)."""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.parsing.places import PlaceResolver
from app.parsing.rules import RulesParser
from app.parsing.service import TripParseService
from app.providers.base import LLMProvider
from app.providers.ollama import OllamaProvider
from app.regions import get_region_config
from app.regions.loader import resolve_region_path
from app.trips.corridor import load_corridor


@lru_cache(maxsize=1)
def get_parse_service() -> TripParseService:
    region = get_region_config()
    corridor = load_corridor(
        resolve_region_path(f"data/regions/{region.region_id}-demo-corridor.yaml")
    )
    settings = get_settings()
    rules = RulesParser()
    parser: LLMProvider = (
        OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
        if settings.ollama_model
        else rules
    )
    return TripParseService(
        parser=parser,
        fallback=rules,
        resolver=PlaceResolver(corridor),
        corridor=corridor,
        timezone=ZoneInfo(region.timezone),
    )
