"""The demo corridor definition (data/regions/<region>-demo-corridor.yaml)."""

from __future__ import annotations

import math
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.pricing.models import Sourced
from app.providers.base import LatLon


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Place(_Strict):
    id: str
    label: str
    lat: float
    lng: float
    in_congestion_relief_zone: bool | None = None
    """Human-checked fact; None = unknown (the toll is then reported unknown)."""
    parking_area: str | None = None

    @property
    def point(self) -> LatLon:
        return LatLon(self.lat, self.lng)


class SubwayAssumptions(_Strict):
    access_minutes: float = Field(ge=0)
    mph: float = Field(gt=0)


class CommuteAssumptions(Sourced):
    """Daily round-trip view: when the commuter heads home, and how many days a year they
    commute (for the monthly and annual figures)."""

    default_return_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    working_days_per_year: int = Field(gt=0, le=366)


class Corridor(_Strict):
    corridor_id: str
    name: str
    transit_feed: str
    hub_station: str
    assumed_parking_hours: float = Field(gt=0, le=24)
    walk_mph: float = Field(gt=0)
    walk_detour_factor: float = Field(ge=1)
    max_walk_miles: float = Field(ge=0)
    hub_boarding_buffer_minutes: float = Field(ge=0)
    subway: SubwayAssumptions
    commute: CommuteAssumptions
    origins: tuple[Place, ...]
    destinations: tuple[Place, ...]

    def place_near(self, point: LatLon, within_m: float = 250) -> Place | None:
        """The preset at this point, if any — presets carry the human-checked facts."""
        for place in (*self.destinations, *self.origins):
            if haversine_m(place.point, point) <= within_m:
                return place
        return None


def load_corridor(path: Path) -> Corridor:
    return Corridor.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def haversine_m(a: LatLon, b: LatLon) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))
