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


class Preferences(_Request):
    sort_mode: Literal["best_overall", "fastest", "cheapest"] = "best_overall"


class TripSearchRequest(_Request):
    origin: LatLng
    destination: LatLng
    time_mode: Literal["leave_now", "leave_at", "arrive_by"]
    target_time: datetime | None = None
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


class RouteOption(BaseModel):
    route_id: str
    label: str | None
    summary: str
    total_minutes: float
    drive_minutes: float
    transit_minutes: float
    walk_minutes: float
    wait_minutes: float
    drive_miles: float
    transfer_count: int
    cost_breakdown: CostBreakdown
    parking: RouteParking | None
    warnings: list[str]
    explanation: Explanation
    legs: list[RouteLeg]


class TripSearchResponse(BaseModel):
    request_id: str
    routes: list[RouteOption]
    sort_options: list[str]
    disclaimers: list[str]
