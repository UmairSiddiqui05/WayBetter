"""Schemas for the price data files. Unknown keys are errors, like the region config."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DataStatus(StrEnum):
    """The subset of the provenance enum (N-02) that stored price data can carry."""

    SCHEDULED = "scheduled"
    """Published by the operator (tariff, fare chart, posted rate)."""
    ESTIMATED = "estimated"
    """An average or derived figure applied to this trip."""
    UNKNOWN = "unknown"
    """No sourced value. The amount must be null — never a plausible guess."""


Money = float


class Source(StrictModel):
    name: str | None = None
    url: str | None = None
    secondary_url: str | None = None
    index_url: str | None = None
    operator_url: str | None = None
    retrieved: date
    notes: str | None = None


class EffectiveDated(StrictModel):
    currency: Literal["USD"]
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def _ordered_dates(self) -> EffectiveDated:
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to is before effective_from")
        return self

    def in_effect(self, on: date) -> bool:
        return self.effective_from <= on and (self.effective_to is None or on <= self.effective_to)


class Sourced(StrictModel):
    """A value with its provenance. Scheduled/estimated values must name a source URL."""

    status: DataStatus
    human_verified: bool = False
    source: Source

    @model_validator(mode="after")
    def _sourced_unless_unknown(self) -> Sourced:
        if self.status is not DataStatus.UNKNOWN and not self.source.url:
            raise ValueError(f"a {self.status.value} value must carry a source url (N-09)")
        return self


# --- Fares -------------------------------------------------------------------


class StationFare(StrictModel):
    from_station: str
    to_station: str
    fare_zone: int | None = None
    adult_one_way: Money = Field(gt=0)


class RailFares(EffectiveDated, Sourced):
    kind: Literal["rail_fares"]
    agency: str
    feed_id: str
    fares: tuple[StationFare, ...]


class FlatFare(EffectiveDated, Sourced):
    kind: Literal["flat_fare"]
    agency: str
    feed_id: str
    adult_base_fare: Money = Field(gt=0)


# --- Tolls -------------------------------------------------------------------

TimeWindow = tuple[str, str]


class PeakWindows(StrictModel):
    """Local-time windows ("HH:MM" 24h). Outside them the off-peak rate applies."""

    weekday: tuple[TimeWindow, ...]
    weekend: tuple[TimeWindow, ...]


class CrossingRates(StrictModel):
    ezpass_peak: Money = Field(ge=0)
    ezpass_off_peak: Money = Field(ge=0)
    toll_by_mail: Money = Field(ge=0)


class CrossingToll(EffectiveDated, Sourced):
    kind: Literal["crossing_toll"]
    facility_id: str
    operator: str
    direction_tolled: Literal["into_new_york", "both"]
    route_match_names: tuple[str, ...]
    """Road names that identify this facility on a driving route."""
    rates: CrossingRates
    peak_windows: PeakWindows


class ZoneRates(StrictModel):
    ezpass_peak: Money = Field(ge=0)
    ezpass_overnight: Money = Field(ge=0)


class CrossingCredit(StrictModel):
    max_credit_peak: Money = Field(ge=0)
    qualifying_facilities: tuple[str, ...]


class ZoneToll(EffectiveDated, Sourced):
    kind: Literal["zone_toll"]
    facility_id: str
    operator: str
    rates: ZoneRates
    charged_once_per_day: bool
    peak_windows: PeakWindows
    crossing_credit: CrossingCredit


class Interchange(StrictModel):
    id: str
    name: str
    lat: float
    lon: float


class TicketRate(StrictModel):
    entry: str
    exit: str
    ezpass_peak: Money = Field(ge=0)
    nj_ezpass_off_peak: Money = Field(ge=0)
    cash: Money = Field(ge=0)


class TicketToll(EffectiveDated, Sourced):
    """A closed toll road priced by entry and exit interchange (e.g. NJ Turnpike)."""

    kind: Literal["ticket_toll"]
    facility_id: str
    operator: str
    road_ref_match: str
    """Substring of the route step `ref` that marks a step as on this road."""
    peak_windows: PeakWindows
    interchanges: tuple[Interchange, ...]
    rates: tuple[TicketRate, ...]

    def rate(self, entry: str, exit_: str) -> TicketRate | None:
        return next((r for r in self.rates if r.entry == entry and r.exit == exit_), None)


# --- Parking -----------------------------------------------------------------


class RateTier(StrictModel):
    max_hours: float = Field(gt=0, le=24)
    usd: Money = Field(ge=0)


class ParkingLot(Sourced):
    lot_id: str
    station: str
    name: str
    operator: str
    address: str
    capacity: int | None = Field(default=None, ge=0)
    rate_tiers: tuple[RateTier, ...]

    @model_validator(mode="after")
    def _unknown_means_no_price(self) -> ParkingLot:
        if (self.status is DataStatus.UNKNOWN) != (not self.rate_tiers):
            raise ValueError(
                f"{self.lot_id}: rate_tiers must be empty exactly when status is unknown"
            )
        hours = [t.max_hours for t in self.rate_tiers]
        if hours != sorted(hours):
            raise ValueError(f"{self.lot_id}: rate tiers must be ordered by max_hours")
        return self

    def daily_cost(self, hours: float) -> Money | None:
        """Cost of a stay of `hours`, or None when the price is unknown or the stay is too long."""
        for tier in self.rate_tiers:
            if hours <= tier.max_hours:
                return tier.usd
        return None


class ParkingLots(EffectiveDated):
    kind: Literal["parking_lots"]
    lots: tuple[ParkingLot, ...]


class DestinationArea(Sourced):
    area_id: str
    name: str
    daily_usd: Money | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _unknown_means_no_price(self) -> DestinationArea:
        if (self.status is DataStatus.UNKNOWN) != (self.daily_usd is None):
            raise ValueError(
                f"{self.area_id}: daily_usd must be null exactly when status is unknown"
            )
        return self


class DestinationParking(EffectiveDated):
    kind: Literal["destination_parking"]
    areas: tuple[DestinationArea, ...]


# --- Vehicle -----------------------------------------------------------------


class GasolinePrice(Sourced):
    usd_per_gallon: Money = Field(gt=0)


class FuelEconomy(Sourced):
    mpg: float = Field(gt=0)


class VehicleDefaults(EffectiveDated):
    kind: Literal["vehicle_defaults"]
    gasoline: GasolinePrice
    fuel_economy: FuelEconomy
    cost_scope: str
