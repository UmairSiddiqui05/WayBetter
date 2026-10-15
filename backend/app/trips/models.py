"""API models for POST /trip/search — a subset of docs/api-spec.yaml, same field names."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Provenance(StrEnum):
    """N-02. Every user-facing datum carries one."""

    LIVE = "live"
    SCHEDULED = "scheduled"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"
    USER_REPORTED = "user_reported"
    AI_GENERATED = "ai_generated"


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LatLng(_Request):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    label: str | None = None


class VehicleProfile(_Request):
    toll_payment: Literal["ezpass", "cash"] = "ezpass"
    mpg: float | None = Field(default=None, gt=0, le=150)
    """The user's own fuel economy; None = the data-file average. Shown as user_reported."""
    fuel_price_per_gallon: float | None = Field(default=None, gt=0, le=20)
    """The user's own gas price; None = the data-file regional average."""


SortMode = Literal[
    "best_overall",
    "fastest",
    "cheapest",
    "least_driving",
    "most_driving",
    "fewest_transfers",
    "cleanest",
]


class Preferences(_Request):
    sort_mode: SortMode = "best_overall"
    avoid_tolls: bool = False
    """Hide options whose driving pays a toll (each listed in filtered_out with why)."""
    max_walk_minutes: int | None = Field(default=None, ge=0, le=120)
    """Hide options that walk longer than this on the morning trip."""


class TripSearchRequest(_Request):
    origin: LatLng
    destination: LatLng
    time_mode: Literal["leave_now", "leave_at", "arrive_by"]
    target_time: datetime | None = None
    return_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    """Local "HH:MM" the commuter heads home the same day; None = the corridor default."""
    preferences: Preferences = Preferences()
    vehicle_profile: VehicleProfile = VehicleProfile()


class MoneyEstimate(BaseModel):
    amount: float | None
    provenance: Provenance
    note: str | None = None


class CostBreakdown(BaseModel):
    currency: str = "USD"
    gas_or_ev: MoneyEstimate
    parking: MoneyEstimate
    transit_fare: MoneyEstimate
    tolls: MoneyEstimate
    congestion_fee: MoneyEstimate
    total: float
    """Sum of the known components. Unknown components are named in the route warnings."""


class MapLink(BaseModel):
    """Hand the drive to a map app (F-17). The URL comes from a region config template."""

    app_id: str
    label: str
    url: str


class RouteLeg(BaseModel):
    leg_id: str
    mode: Literal["car", "transit", "walk"]
    start_location: LatLng
    end_location: LatLng
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    distance_miles: float | None = None
    agency: str | None = None
    route_name: str | None = None
    headsign: str | None = None
    polyline: str | None = None
    time_provenance: Provenance
    map_links: list[MapLink] = []
    """Car legs only: open the same drive in Google Maps / Apple Maps."""


class ParkingFacility(BaseModel):
    parking_id: str
    station_id: str
    name: str
    location: LatLng
    type: Literal["park_and_ride", "garage", "lot", "street"]
    capacity: int | None
    price_daily: MoneyEstimate
    provenance: Provenance
    source_url: str | None
    last_verified_at: str | None


class RouteParking(BaseModel):
    facility: ParkingFacility
    confidence: Literal["high", "medium", "low", "unknown"]


class Explanation(BaseModel):
    text: str
    provenance: Provenance


class Savings(BaseModel):
    """How much less this option costs than driving all the way, per period."""

    daily: MoneyEstimate
    monthly: MoneyEstimate
    annual: MoneyEstimate


class RoundTrip(BaseModel):
    """The daily commute: this option's morning trip plus the evening trip home."""

    return_summary: str
    return_legs: list[RouteLeg]
    return_minutes: float
    daily_minutes: float
    return_cost_breakdown: CostBreakdown
    """The evening trip alone. Once-a-day charges (parking, congestion toll) show $0 here."""
    daily_cost_breakdown: CostBreakdown
    """Morning + evening, each once-a-day charge counted once."""
    monthly_cost: MoneyEstimate
    annual_cost: MoneyEstimate
    savings_vs_drive: Savings | None
    """None for the drive-all-the-way option itself, or when there is no drive baseline."""


BadgeId = Literal[
    "best_overall", "fastest", "cheapest", "least_driving", "fewest_transfers", "cleanest"
]


class Badge(BaseModel):
    """A server-awarded tag (N-01). Only a unique winner gets one; a tie gets none."""

    id: BadgeId
    text: str


class RouteOption(BaseModel):
    route_id: str
    badges: list[Badge]
    summary: str
    total_minutes: float
    drive_minutes: float
    transit_minutes: float
    walk_minutes: float
    wait_minutes: float
    drive_miles: float
    transfer_count: int
    cost_breakdown: CostBreakdown
    emissions_kg: MoneyEstimate
    """Tailpipe CO2 for the morning trip in kg (amount is kg, not dollars), estimated."""
    parking: RouteParking | None
    warnings: list[str]
    explanation: Explanation
    legs: list[RouteLeg]
    round_trip: RoundTrip | None = None
    """None when no trip home could be found (e.g. no train after the return time)."""


class FilteredRoute(BaseModel):
    """An option the request's filters hid, and why — never silently dropped (F-07)."""

    route_id: str
    summary: str
    reasons: list[str]


class TripSearchResponse(BaseModel):
    request_id: str
    routes: list[RouteOption]
    filtered_out: list[FilteredRoute] = []
    sort_options: list[str]
    disclaimers: list[str]
