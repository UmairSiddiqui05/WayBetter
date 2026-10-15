"""Provider interfaces (N-04). Vendor SDKs and URLs never leak past an adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, NamedTuple, Protocol

if TYPE_CHECKING:
    from app.parsing.models import ParsedTrip


class LatLon(NamedTuple):
    lat: float
    lon: float


class ProviderError(RuntimeError):
    """An upstream provider failed or returned something unusable."""


@dataclass(frozen=True, slots=True)
class DriveStep:
    """One maneuver of a driving route — enough to detect tolled facilities."""

    name: str
    ref: str
    exits: str
    maneuver: str
    location: LatLon
    distance_m: float


@dataclass(frozen=True, slots=True)
class DriveRoute:
    duration_s: float
    distance_m: float
    polyline: str
    """Encoded polyline (precision 5) for map display."""
    steps: tuple[DriveStep, ...]


@dataclass(frozen=True, slots=True)
class TransitTrip:
    trip_id: str
    agency: str
    route_name: str
    headsign: str
    from_station: str
    to_station: str
    departure: datetime
    arrival: datetime
    shape_id: str | None


class DrivingProvider(Protocol):
    def route(self, origin: LatLon, destination: LatLon) -> DriveRoute: ...


class TransitProvider(Protocol):
    def next_trip(
        self, from_station: str, to_station: str, depart_after: datetime
    ) -> TransitTrip | None:
        """The scheduled direct trip (no transfer) leaving `from_station` at or after
        `depart_after` that ARRIVES at `to_station` first. Stations are canonical IDs (N-03)."""
        ...

    def trip_polyline(self, trip: TransitTrip) -> str | None:
        """Encoded polyline of the ridden segment, or None when the feed has no shape."""
        ...


class LLMProvider(Protocol):
    """Reads a trip request in plain words into ParsedTrip — words only, never coordinates,
    prices, schedules or routes (D-11). Raises ProviderError on any failure."""

    name: str

    def parse_trip(self, text: str) -> ParsedTrip: ...


@dataclass(frozen=True, slots=True)
class GeocodeResult:
    name: str
    """The feature's own name ("DeLucia's Brick Oven Pizza"), or "<number> <street>" for an
    address with no name."""
    town: str | None
    """Town / city / village / borough from the address, when the geocoder knows it."""
    display_name: str
    point: LatLon
    kind: str
    """Geocoder category, e.g. "amenity", "place", "boundary", "building"."""
    address_line: str | None = None
    """"<number> <street>" when known ("429 11th Avenue"), even for a named feature."""
    localities: tuple[str, ...] = ()
    """Every place name in the address (town, city, borough, suburb...): "Manhattan" and
    "New York" both describe 429 11th Ave."""


class GeocodingProvider(Protocol):
    attribution: str

    def search(self, query: str) -> list[GeocodeResult]:
        """Candidates for free text, inside the region. Raises ProviderError if unreachable."""
        ...
