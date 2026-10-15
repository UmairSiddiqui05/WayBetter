"""Trip search: drive-all-the-way vs park-and-ride on one corridor (F-01..F-03 subset).

Flow per request:
  1. Drive all the way: one driving route; fuel + tolls + congestion fee + garage.
  2. Each park-and-ride lot: drive to the lot, park and walk to the platform (region buffer),
     next scheduled train to the hub, then walk or subway to the destination.
  3. The daily commute: each option's evening trip home at the return time, then daily,
     monthly and annual costs (once-a-day charges counted once) and savings versus driving.
  4. Rank on the morning trip, label the winners, and explain from the computed numbers.
All of it is server-side; the client only renders this payload (N-01).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.pricing import DataStatus, PricingData
from app.pricing.models import ParkingLot, RailFares, StationFare, VehicleDefaults
from app.providers.base import DriveRoute, DrivingProvider, LatLon, ProviderError, TransitProvider
from app.regions.schema import RegionConfig
from app.trips import costs
from app.trips.corridor import Corridor, Place, haversine_m
from app.trips.models import (
    CostBreakdown,
    Explanation,
    LatLng,
    MoneyEstimate,
    ParkingFacility,
    Provenance,
    RoundTrip,
    RouteLeg,
    RouteOption,
    RouteParking,
    Savings,
    TripSearchRequest,
    TripSearchResponse,
)

SORT_OPTIONS = ["best_overall", "fastest", "cheapest"]


class TripSearchError(ValueError):
    """The request cannot be served (outside the region, unsupported mode)."""


@dataclass(frozen=True)
class Station:
    station_id: str
    name: str
    point: LatLon


@dataclass
class _Option:
    route: RouteOption
    known_cost: float
    complete_cost: bool


@dataclass(frozen=True)
class _Evening:
    """The trip home, before it is folded into the option's RoundTrip."""

    summary: str
    legs: list[RouteLeg]
    costs: CostBreakdown
    warnings: list[str]


def _ll(point: LatLon, label: str | None = None) -> LatLng:
    return LatLng(lat=point.lat, lng=point.lon, label=label)


def _minutes(delta: timedelta) -> float:
    return round(delta.total_seconds() / 60, 1)


def _clock(at: datetime) -> str:
    return f"{at:%I:%M %p}".lstrip("0")


def _money(est: MoneyEstimate) -> str:
    return "unknown" if est.amount is None else f"${est.amount:,.2f}"


def _free(note: str) -> MoneyEstimate:
    return MoneyEstimate(amount=0.0, provenance=Provenance.SCHEDULED, note=note)


def _parts(breakdown: CostBreakdown) -> dict[str, MoneyEstimate]:
    return {
        "fuel": breakdown.gas_or_ev,
        "parking": breakdown.parking,
        "transit fare": breakdown.transit_fare,
        "tolls": breakdown.tolls,
        "congestion fee": breakdown.congestion_fee,
    }


def _breakdown(
    fuel: MoneyEstimate,
    parking: MoneyEstimate,
    fare: MoneyEstimate,
    tolls: MoneyEstimate,
    zone: MoneyEstimate,
) -> CostBreakdown:
    return CostBreakdown(
        gas_or_ev=fuel,
        parking=parking,
        transit_fare=fare,
        tolls=tolls,
        congestion_fee=zone,
        total=costs.sum_known(fuel, parking, fare, tolls, zone),
    )


def _both_trips(morning: MoneyEstimate, evening: MoneyEstimate) -> MoneyEstimate:
    """One cost line of the daily commute. A once-a-day charge shows $0 on the evening trip."""
    if morning.amount is None or evening.amount is None:
        amount = None
    else:
        amount = round(morning.amount + evening.amount, 2)
    if morning.amount == 0 and evening.amount == 0:
        same = morning.note == evening.note
        note = morning.note if same else f"Morning: {morning.note}. Evening: {evening.note}"
    elif evening.amount == 0:
        note = f"Once a day: {morning.note}"
    else:
        note = f"Morning {_money(morning)} + evening {_money(evening)}"
    return MoneyEstimate(
        amount=amount, provenance=costs.worst(morning.provenance, evening.provenance), note=note
    )


def _total(breakdown: CostBreakdown) -> MoneyEstimate:
    """The breakdown's total, or unknown when any part is unknown (a partial sum is not a total)."""
    parts = _parts(breakdown)
    missing = [name for name, est in parts.items() if est.amount is None]
    if missing:
        return MoneyEstimate(
            amount=None, provenance=Provenance.UNKNOWN, note=f"Excludes {', '.join(missing)}"
        )
    return MoneyEstimate(
        amount=breakdown.total, provenance=costs.worst(*(e.provenance for e in parts.values()))
    )


def _difference(drive: MoneyEstimate, option: MoneyEstimate, period: str) -> MoneyEstimate:
    if drive.amount is None or option.amount is None:
        return MoneyEstimate(
            amount=None,
            provenance=Provenance.UNKNOWN,
            note=f"Not computed: a {period} cost is unknown",
        )
    return MoneyEstimate(
        amount=round(drive.amount - option.amount, 2),
        provenance=costs.worst(drive.provenance, option.provenance),
        note=f"Driving {_money(drive)} minus this option {_money(option)}",
    )


class TripSearchService:
    def __init__(
        self,
        region: RegionConfig,
        corridor: Corridor,
        pricing: PricingData,
        stations: dict[str, Station],
        driving: DrivingProvider,
        transit: TransitProvider,
    ) -> None:
        self._region = region
        self._corridor = corridor
        self._pricing = pricing
        self._stations = stations
        self._driving = driving
        self._transit = transit
        self._tz = ZoneInfo(region.timezone)

    @property
    def corridor(self) -> Corridor:
        return self._corridor

    @property
    def timezone(self) -> ZoneInfo:
        return self._tz

    @property
    def option_count(self) -> int:
        """Options a complete answer has: drive-all-the-way plus one per lot."""
        return 1 + sum(len(group.lots) for group in self._pricing.parking_lots)

    # -- entry point ---------------------------------------------------------------

    def search(self, request: TripSearchRequest, now: datetime) -> TripSearchResponse:
        origin = LatLon(request.origin.lat, request.origin.lng)
        destination = LatLon(request.destination.lat, request.destination.lng)
        box = self._region.bounding_box
        for name, point in (("origin", origin), ("destination", destination)):
            if not box.contains(point.lat, point.lon):
                raise TripSearchError(f"{name} is outside the {self._region.name} service area")
        if request.time_mode == "arrive_by":
            raise TripSearchError("arrive_by is not supported in this demo; use leave_at")
        if request.time_mode == "leave_at" and request.target_time is None:
            raise TripSearchError("leave_at needs target_time")
        depart = (
            request.target_time if request.time_mode == "leave_at" and request.target_time else now
        )
        if depart.tzinfo is None:
            depart = depart.replace(tzinfo=self._tz)
        depart = depart.astimezone(self._tz)
        return_at = self._return_at(depart, request.return_time)
        payment = request.vehicle_profile.toll_payment
        dest_place = self._corridor.place_near(destination)

        options: list[_Option] = []
        warnings_global: list[str] = []
        try:
            options.append(
                self._drive_all_the_way(origin, destination, dest_place, depart, return_at, payment)
            )
        except ProviderError as exc:
            warnings_global.append(f"Driving baseline unavailable: {exc}")
        for group in self._pricing.parking_lots:
            for lot in group.lots:
                try:
                    option = self._park_and_ride(
                        lot, origin, destination, dest_place, depart, return_at, payment
                    )
                except ProviderError as exc:
                    warnings_global.append(f"{lot.name}: {exc}")
                    continue
                if option:
                    options.append(option)

        self._add_savings(options)
        ranked = self._rank(options, request.preferences.sort_mode)
        self._label_and_explain(ranked)
        return TripSearchResponse(
            request_id=str(uuid.uuid4()),
            routes=[o.route for o in ranked],
            sort_options=SORT_OPTIONS,
            disclaimers=self._disclaimers() + warnings_global,
        )

    def _return_at(self, depart: datetime, requested: str | None) -> datetime:
        hhmm = requested or self._corridor.commute.default_return_time
        hour, minute = (int(part) for part in hhmm.split(":"))
        at = depart.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if at <= depart:
            raise TripSearchError(
                "The head-home time must be later the same day than the departure"
            )
        return at

    # -- options -------------------------------------------------------------------

    def _vehicle(self) -> VehicleDefaults:
        return self._pricing.vehicle_defaults[0]

    def _tolls(
        self, route: DriveRoute, depart: datetime, payment: str
    ) -> tuple[MoneyEstimate, set[str], list[str]]:
        lines: list[costs.TollLine] = []
        for ticket in self._pricing.ticket_tolls:
            line = costs.ticket_toll(route, ticket, depart, payment)
            if line:
                lines.append(line)
        for barrier in self._pricing.barrier_tolls:
            line = costs.barrier_toll(route, barrier, depart, payment)
            if line:
                lines.append(line)
        for crossing in self._pricing.crossing_tolls:
            line = costs.crossing_toll(route, crossing, depart, payment)
            if line:
                lines.append(line)
        if not lines:
            return (
                MoneyEstimate(amount=0.0, provenance=Provenance.SCHEDULED, note="No tolled roads"),
                set(),
                [],
            )
        unknown = [line.note for line in lines if line.amount is None]
        amount = round(sum(line.amount for line in lines if line.amount is not None), 2)
        estimate = MoneyEstimate(
            amount=None if unknown and amount == 0 else amount,
            provenance=costs.worst(*(line.provenance for line in lines)),
            note="; ".join(
                f"{line.note}: ${line.amount:.2f}" if line.amount is not None else line.note
                for line in lines
            ),
        )
        return estimate, {line.facility_id for line in lines}, unknown

    def _drive_all_the_way(
        self,
        origin: LatLon,
        destination: LatLon,
        dest_place: Place | None,
        depart: datetime,
        return_at: datetime,
        payment: str,
    ) -> _Option:
        route = self._driving.route(origin, destination)
        arrive = depart + timedelta(seconds=route.duration_s)
        fuel = costs.fuel_cost(route.distance_m, self._vehicle())
        tolls, facilities, unknown_tolls = self._tolls(route, depart, payment)
        zone = costs.zone_toll(
            self._pricing.zone_tolls[0],
            dest_place.in_congestion_relief_zone if dest_place else None,
            arrive,
            facilities,
            payment,
        )
        parking = self._destination_parking(dest_place)
        none = MoneyEstimate(amount=0.0, provenance=Provenance.SCHEDULED, note="No transit")
        breakdown = CostBreakdown(
            gas_or_ev=fuel,
            parking=parking,
            transit_fare=none,
            tolls=tolls,
            congestion_fee=zone,
            total=costs.sum_known(fuel, parking, tolls, zone),
        )
        miles = route.distance_m / costs.METERS_PER_MILE
        leg = RouteLeg(
            leg_id="drive-1",
            mode="car",
            start_location=_ll(origin),
            end_location=_ll(destination),
            start_time=depart,
            end_time=arrive,
            duration_minutes=_minutes(arrive - depart),
            distance_miles=round(miles, 1),
            polyline=route.polyline,
            time_provenance=Provenance.ESTIMATED,
        )
        warnings = self._unknown_warnings(breakdown) + [
            f"Toll not priced: {n}" for n in unknown_tolls
        ]
        warnings.append("Drive time is free-flow (no live traffic); rush hour is usually slower.")
        round_trip = None
        try:
            evening = self._drive_home(origin, destination, max(return_at, arrive), payment)
            round_trip = self._round_trip(evening, breakdown, leg.duration_minutes, None)
            warnings += evening.warnings
        except ProviderError as exc:
            warnings.append(f"Trip home unavailable: {exc}")
        option = RouteOption(
            route_id="drive",
            label=None,
            summary="Drive all the way",
            total_minutes=leg.duration_minutes,
            drive_minutes=leg.duration_minutes,
            transit_minutes=0,
            walk_minutes=0,
            wait_minutes=0,
            drive_miles=round(miles, 1),
            transfer_count=0,
            cost_breakdown=breakdown,
            parking=None,
            warnings=warnings,
            explanation=Explanation(text="", provenance=Provenance.ESTIMATED),
            legs=[leg],
            round_trip=round_trip,
        )
        return _Option(
            option, breakdown.total, not self._unknown_warnings(breakdown) and not unknown_tolls
        )

    def _drive_home(
        self, origin: LatLon, destination: LatLon, leave: datetime, payment: str
    ) -> _Evening:
        route = self._driving.route(destination, origin)
        home = leave + timedelta(seconds=route.duration_s)
        tolls, _, unknown_tolls = self._tolls(route, leave, payment)
        zone = self._pricing.zone_tolls[0]
        evening = _breakdown(
            costs.fuel_cost(route.distance_m, self._vehicle()),
            _free("Day rate, already paid on the morning trip"),
            _free("No transit"),
            tolls,
            _free(
                "Charged once per day, already paid on the morning trip"
                if zone.charged_once_per_day
                else "Leaving the zone is not charged"
            ),
        )
        leg = RouteLeg(
            leg_id="home-drive-1",
            mode="car",
            start_location=_ll(destination),
            end_location=_ll(origin),
            start_time=leave,
            end_time=home,
            duration_minutes=_minutes(home - leave),
            distance_miles=round(route.distance_m / costs.METERS_PER_MILE, 1),
            polyline=route.polyline,
            time_provenance=Provenance.ESTIMATED,
        )
        return _Evening(
            summary=f"Leave {_clock(leave)}, drive home, arrive {_clock(home)}",
            legs=[leg],
            costs=evening,
            warnings=self._home_warnings(evening, unknown_tolls),
        )

    def _home_warnings(self, evening: CostBreakdown, unknown_tolls: list[str]) -> list[str]:
        return [f"Trip home: {w}" for w in self._unknown_warnings(evening)] + [
            f"Trip home toll not priced: {n}" for n in unknown_tolls
        ]

    def _round_trip(
        self,
        evening: _Evening,
        morning: CostBreakdown,
        morning_minutes: float,
        rail: tuple[RailFares, StationFare] | None,
    ) -> RoundTrip:
        daily = _breakdown(
            *(
                _both_trips(m, e)
                for m, e in zip(
                    _parts(morning).values(), _parts(evening.costs).values(), strict=True
                )
            )
        )
        monthly, annual = self._periods(daily, rail)
        return_minutes = _minutes(evening.legs[-1].end_time - evening.legs[0].start_time)
        return RoundTrip(
            return_summary=evening.summary,
            return_legs=evening.legs,
            return_minutes=return_minutes,
            daily_minutes=round(morning_minutes + return_minutes, 1),
            return_cost_breakdown=evening.costs,
            daily_cost_breakdown=daily,
            monthly_cost=monthly,
            annual_cost=annual,
            savings_vs_drive=None,
        )

    def _periods(
        self, daily: CostBreakdown, rail: tuple[RailFares, StationFare] | None
    ) -> tuple[MoneyEstimate, MoneyEstimate]:
        """Monthly and annual cost. Rail uses the monthly pass when it beats one-way tickets."""
        commute = self._corridor.commute
        per_day = _total(daily)
        if per_day.amount is None:
            unknown = MoneyEstimate(
                amount=None, provenance=Provenance.UNKNOWN, note=f"Daily cost {per_day.note}"
            )
            return unknown, unknown
        days = commute.working_days_per_year / 12
        provenance = costs.worst(per_day.provenance, costs.provenance_of(commute.status))
        monthly = per_day.amount * days
        note = f"{days:.1f} working days a month x ${per_day.amount:.2f} a day"
        table, fare = rail if rail else (None, None)
        monthly_pass = fare.monthly_pass if fare else None
        if table and fare and monthly_pass is not None:
            tickets = 2 * fare.adult_one_way * days
            if monthly_pass < tickets:
                other = per_day.amount - 2 * fare.adult_one_way
                monthly = other * days + monthly_pass
                note = (
                    f"{days:.1f} working days x ${other:.2f} a day + ${monthly_pass:.2f} "
                    f"{table.agency} monthly pass (cheaper than {2 * days:.0f} one-way tickets, "
                    f"${tickets:,.2f})"
                )
        monthly = round(monthly, 2)
        return (
            MoneyEstimate(amount=monthly, provenance=provenance, note=note),
            MoneyEstimate(
                amount=round(monthly * 12, 2),
                provenance=provenance,
                note=f"12 months x ${monthly:,.2f} ({commute.working_days_per_year} working days)",
            ),
        )

    @staticmethod
    def _add_savings(options: list[_Option]) -> None:
        drive = next((o.route.round_trip for o in options if o.route.route_id == "drive"), None)
        if drive is None:
            return
        for o in options:
            mine = o.route.round_trip
            if mine is None or o.route.route_id == "drive":
                continue
            mine.savings_vs_drive = Savings(
                daily=_difference(
                    _total(drive.daily_cost_breakdown), _total(mine.daily_cost_breakdown), "daily"
                ),
                monthly=_difference(drive.monthly_cost, mine.monthly_cost, "monthly"),
                annual=_difference(drive.annual_cost, mine.annual_cost, "annual"),
            )

    def _destination_parking(self, dest_place: Place | None) -> MoneyEstimate:
        area_id = dest_place.parking_area if dest_place else None
        for group in self._pricing.destination_parking:
            for area in group.areas:
                if area.area_id == area_id:
                    return MoneyEstimate(
                        amount=area.daily_usd,
                        provenance=costs.provenance_of(area.status),
                        note=area.name,
                    )
        return MoneyEstimate(
            amount=None, provenance=Provenance.UNKNOWN, note="No parking data for this destination"
        )

    def _park_and_ride(
        self,
        lot: ParkingLot,
        origin: LatLon,
        destination: LatLon,
        dest_place: Place | None,
        depart: datetime,
        return_at: datetime,
        payment: str,
    ) -> _Option | None:
        station = self._stations.get(lot.station)
        hub = self._stations.get(self._corridor.hub_station)
        if not station or not hub:
            return None
        drive = self._driving.route(origin, station.point)
        at_lot = depart + timedelta(seconds=drive.duration_s)
        on_platform = at_lot + timedelta(minutes=self._region.default_parking_buffer_minutes)
        trip = self._transit.next_trip(lot.station, self._corridor.hub_station, on_platform)
        if trip is None:
            return None
        legs: list[RouteLeg] = []
        drive_miles = drive.distance_m / costs.METERS_PER_MILE
        legs.append(
            RouteLeg(
                leg_id="drive-1",
                mode="car",
                start_location=_ll(origin),
                end_location=_ll(station.point, station.name),
                start_time=depart,
                end_time=at_lot,
                duration_minutes=_minutes(at_lot - depart),
                distance_miles=round(drive_miles, 1),
                polyline=drive.polyline,
                time_provenance=Provenance.ESTIMATED,
            )
        )
        legs.append(
            RouteLeg(
                leg_id="walk-1",
                mode="walk",
                start_location=_ll(station.point),
                end_location=_ll(station.point, station.name),
                start_time=at_lot,
                end_time=on_platform,
                duration_minutes=_minutes(on_platform - at_lot),
                time_provenance=Provenance.ESTIMATED,
            )
        )
        legs.append(
            RouteLeg(
                leg_id="transit-1",
                mode="transit",
                start_location=_ll(station.point, station.name),
                end_location=_ll(hub.point, hub.name),
                start_time=trip.departure,
                end_time=trip.arrival,
                duration_minutes=_minutes(trip.arrival - trip.departure),
                agency=trip.agency,
                route_name=trip.route_name,
                headsign=trip.headsign,
                polyline=self._transit.trip_polyline(trip),
                time_provenance=Provenance.SCHEDULED,
            )
        )
        last_leg, subway_fare = self._last_mile(hub, destination, trip.arrival)
        legs.append(last_leg)

        fuel = costs.fuel_cost(drive.distance_m, self._vehicle())
        tolls, _, unknown_tolls = self._tolls(drive, depart, payment)
        parking_cost = lot.daily_cost(self._corridor.assumed_parking_hours)
        parking = MoneyEstimate(
            amount=parking_cost,
            provenance=costs.provenance_of(lot.status)
            if parking_cost is not None
            else Provenance.UNKNOWN,
            note=f"{lot.name}, {self._corridor.assumed_parking_hours:g} h",
        )
        transit_fare = self._fares(self._rail_fare(lot.station), subway_fare)
        no_zone = MoneyEstimate(
            amount=0.0, provenance=Provenance.SCHEDULED, note="Car stays outside the zone"
        )
        breakdown = CostBreakdown(
            gas_or_ev=fuel,
            parking=parking,
            transit_fare=transit_fare,
            tolls=tolls,
            congestion_fee=no_zone,
            total=costs.sum_known(fuel, parking, transit_fare, tolls),
        )
        wait = _minutes(trip.departure - on_platform)
        walk = legs[1].duration_minutes + (
            last_leg.duration_minutes if last_leg.mode == "walk" else 0
        )
        transit_minutes = legs[2].duration_minutes + (
            last_leg.duration_minutes if last_leg.mode == "transit" else 0
        )
        total = _minutes(last_leg.end_time - depart)
        warnings = self._unknown_warnings(breakdown) + [
            f"Toll not priced: {n}" for n in unknown_tolls
        ]
        if lot.status is DataStatus.ESTIMATED:
            warnings.append(f"{lot.name} price is an estimate: {lot.source.notes or ''}".strip())
        round_trip = None
        try:
            evening = self._ride_home(
                lot,
                station,
                hub,
                origin,
                destination,
                max(return_at, last_leg.end_time),
                at_lot,
                parking,
                payment,
            )
            if evening is None:
                warnings.append(
                    f"No scheduled train from {hub.name.title()} to {station.name.title()} "
                    "after the return time, so there is no daily round-trip figure."
                )
            else:
                round_trip = self._round_trip(
                    evening, breakdown, total, self._rail_row(lot.station)
                )
                warnings += evening.warnings
        except ProviderError as exc:
            warnings.append(f"Trip home unavailable: {exc}")
        option = RouteOption(
            route_id=f"pnr-{lot.lot_id}",
            label=None,
            summary=f"Park at {station.name.title()}, train to {hub.name.title()}",
            total_minutes=total,
            drive_minutes=legs[0].duration_minutes,
            transit_minutes=round(transit_minutes, 1),
            walk_minutes=round(walk, 1),
            wait_minutes=wait,
            drive_miles=round(drive_miles, 1),
            transfer_count=1 if last_leg.mode == "transit" else 0,
            cost_breakdown=breakdown,
            parking=RouteParking(
                facility=ParkingFacility(
                    parking_id=lot.lot_id,
                    station_id=lot.station,
                    name=lot.name,
                    location=_ll(station.point),
                    type="park_and_ride",
                    capacity=lot.capacity,
                    price_daily=parking,
                    provenance=costs.provenance_of(lot.status),
                    source_url=lot.source.url,
                    last_verified_at=lot.source.retrieved.isoformat(),
                ),
                confidence="unknown",  # no occupancy data tonight
            ),
            warnings=warnings,
            explanation=Explanation(text="", provenance=Provenance.ESTIMATED),
            legs=legs,
            round_trip=round_trip,
        )
        return _Option(
            option, breakdown.total, not self._unknown_warnings(breakdown) and not unknown_tolls
        )

    def _ride_home(
        self,
        lot: ParkingLot,
        station: Station,
        hub: Station,
        origin: LatLon,
        destination: LatLon,
        leave: datetime,
        at_lot: datetime,
        morning_parking: MoneyEstimate,
        payment: str,
    ) -> _Evening | None:
        """Walk or subway to the hub, next train out, walk to the car, drive home."""
        city_leg, subway_fare = self._last_mile(hub, destination, leave, toward_hub=True)
        board_after = city_leg.end_time + timedelta(
            minutes=self._corridor.hub_boarding_buffer_minutes
        )
        trip = self._transit.next_trip(hub.station_id, lot.station, board_after)
        if trip is None:
            return None
        at_car = trip.arrival + timedelta(minutes=self._region.default_parking_buffer_minutes)
        drive = self._driving.route(station.point, origin)
        home = at_car + timedelta(seconds=drive.duration_s)
        legs = [
            city_leg,
            RouteLeg(
                leg_id="home-transit-1",
                mode="transit",
                start_location=_ll(hub.point, hub.name),
                end_location=_ll(station.point, station.name),
                start_time=trip.departure,
                end_time=trip.arrival,
                duration_minutes=_minutes(trip.arrival - trip.departure),
                agency=trip.agency,
                route_name=trip.route_name,
                headsign=trip.headsign,
                polyline=self._transit.trip_polyline(trip),
                time_provenance=Provenance.SCHEDULED,
            ),
            RouteLeg(
                leg_id="home-walk-car",
                mode="walk",
                start_location=_ll(station.point, station.name),
                end_location=_ll(station.point),
                start_time=trip.arrival,
                end_time=at_car,
                duration_minutes=_minutes(at_car - trip.arrival),
                time_provenance=Provenance.ESTIMATED,
            ),
            RouteLeg(
                leg_id="home-drive-1",
                mode="car",
                start_location=_ll(station.point, station.name),
                end_location=_ll(origin),
                start_time=at_car,
                end_time=home,
                duration_minutes=_minutes(home - at_car),
                distance_miles=round(drive.distance_m / costs.METERS_PER_MILE, 1),
                polyline=drive.polyline,
                time_provenance=Provenance.ESTIMATED,
            ),
        ]
        tolls, _, unknown_tolls = self._tolls(drive, at_car, payment)
        rail = self._rail_fare(lot.station)
        rail = rail.model_copy(update={"note": f"{rail.note}, same fare in reverse"})
        evening = _breakdown(
            costs.fuel_cost(drive.distance_m, self._vehicle()),
            self._parking_for_stay(lot, at_lot, at_car, morning_parking),
            self._fares(rail, subway_fare),
            tolls,
            _free("Car stays outside the zone"),
        )
        return _Evening(
            summary=(
                f"Leave {_clock(leave)}, {_clock(trip.departure)} train from "
                f"{hub.name.title()}, home {_clock(home)}"
            ),
            legs=legs,
            costs=evening,
            warnings=self._home_warnings(evening, unknown_tolls),
        )

    @staticmethod
    def _parking_for_stay(
        lot: ParkingLot, at_lot: datetime, at_car: datetime, morning: MoneyEstimate
    ) -> MoneyEstimate:
        """The morning priced a typical stay; charge any difference the actual stay makes."""
        hours = (at_car - at_lot).total_seconds() / 3600
        span = f"Car parked {_clock(at_lot)} to {_clock(at_car)} ({hours:.1f} h)"
        actual = lot.daily_cost(hours)
        if actual is None or morning.amount is None:
            return MoneyEstimate(
                amount=None,
                provenance=Provenance.UNKNOWN,
                note=f"{span}: no published rate for this stay",
            )
        extra = round(actual - morning.amount, 2)
        return MoneyEstimate(
            amount=extra,
            provenance=costs.provenance_of(lot.status),
            note=f"{span}, covered by the morning payment"
            if extra == 0
            else f"{span}: ${actual:.2f} rate for the actual stay",
        )

    @staticmethod
    def _fares(rail: MoneyEstimate, subway: MoneyEstimate | None) -> MoneyEstimate:
        if subway is None:
            return rail
        return MoneyEstimate(
            amount=None
            if rail.amount is None or subway.amount is None
            else round(rail.amount + subway.amount, 2),
            provenance=costs.worst(rail.provenance, subway.provenance),
            note=f"{rail.note} + {subway.note}",
        )

    def _rail_row(self, from_station: str) -> tuple[RailFares, StationFare] | None:
        for table in self._pricing.rail_fares:
            for fare in table.fares:
                if (
                    fare.from_station == from_station
                    and fare.to_station == self._corridor.hub_station
                ):
                    return table, fare
        return None

    def _rail_fare(self, from_station: str) -> MoneyEstimate:
        row = self._rail_row(from_station)
        if row is None:
            return MoneyEstimate(
                amount=None, provenance=Provenance.UNKNOWN, note="Rail fare not in data"
            )
        table, fare = row
        return MoneyEstimate(
            amount=fare.adult_one_way,
            provenance=costs.provenance_of(table.status),
            note=f"{table.agency} one-way, zone {fare.fare_zone}",
        )

    def _last_mile(
        self, hub: Station, destination: LatLon, start: datetime, toward_hub: bool = False
    ) -> tuple[RouteLeg, MoneyEstimate | None]:
        """Hub <-> destination on foot or by subway; `toward_hub` is the evening direction."""
        c = self._corridor
        miles = haversine_m(hub.point, destination) / costs.METERS_PER_MILE * c.walk_detour_factor
        ends = (_ll(hub.point, hub.name), _ll(destination))
        begin, finish = (ends[1], ends[0]) if toward_hub else ends
        prefix = "home-" if toward_hub else ""
        if miles <= c.max_walk_miles:
            end = start + timedelta(hours=miles / c.walk_mph)
            leg = RouteLeg(
                leg_id=f"{prefix}walk-2",
                mode="walk",
                start_location=begin,
                end_location=finish,
                start_time=start,
                end_time=end,
                duration_minutes=_minutes(end - start),
                distance_miles=round(miles, 2),
                time_provenance=Provenance.ESTIMATED,
            )
            return leg, None
        end = start + timedelta(minutes=c.subway.access_minutes, hours=miles / c.subway.mph)
        flat = self._pricing.flat_fares[0]
        leg = RouteLeg(
            leg_id=f"{prefix}transit-2",
            mode="transit",
            start_location=begin,
            end_location=finish,
            start_time=start,
            end_time=end,
            duration_minutes=_minutes(end - start),
            distance_miles=round(miles, 2),
            agency=flat.agency,
            route_name="Subway",
            time_provenance=Provenance.ESTIMATED,
        )
        fare = MoneyEstimate(
            amount=flat.adult_base_fare,
            provenance=costs.provenance_of(flat.status),
            note=f"{flat.agency} subway fare",
        )
        return leg, fare

    @staticmethod
    def _unknown_warnings(breakdown: CostBreakdown) -> list[str]:
        parts = {
            "fuel": breakdown.gas_or_ev,
            "parking": breakdown.parking,
            "transit fare": breakdown.transit_fare,
            "tolls": breakdown.tolls,
            "congestion fee": breakdown.congestion_fee,
        }
        return [
            f"Total excludes {name}: unknown ({est.note})"
            for name, est in parts.items()
            if est.amount is None
        ]

    # -- ranking and explanation ------------------------------------------------------

    @staticmethod
    def _rank_keys(options: list[_Option]) -> dict[str, Callable[[_Option], tuple[float, ...]]]:
        """Sort keys per mode. An option with an unknown cost has only a partial total — a lower
        bound — so for cost-based modes it ranks after every option whose total is complete;
        a partial total can never win on price (N-02). Time is always known, so "fastest" is
        unaffected."""
        complete = [o for o in options if o.complete_cost] or options
        min_cost = min((o.known_cost for o in complete), default=0) or 1.0
        min_time = min((o.route.total_minutes for o in options), default=0) or 1.0

        def score(o: _Option) -> float:
            # Equal weight to money and time, each relative to the best available option.
            return o.known_cost / min_cost + o.route.total_minutes / min_time

        def partial(o: _Option) -> float:
            return 0.0 if o.complete_cost else 1.0

        return {
            "fastest": lambda o: (o.route.total_minutes, o.known_cost),
            "cheapest": lambda o: (partial(o), o.known_cost, o.route.total_minutes),
            "best_overall": lambda o: (partial(o), score(o), o.route.total_minutes),
        }

    @classmethod
    def _rank(cls, options: list[_Option], sort_mode: str) -> list[_Option]:
        if not options:
            return []
        keys = cls._rank_keys(options)
        return sorted(options, key=keys.get(sort_mode, keys["best_overall"]))

    @classmethod
    def _label_and_explain(cls, ranked: list[_Option]) -> None:
        if not ranked:
            return
        keys = cls._rank_keys(ranked)
        best = min(ranked, key=keys["best_overall"])
        fastest = min(ranked, key=keys["fastest"])
        badges: dict[str, list[str]] = {o.route.route_id: [] for o in ranked}
        badges[best.route.route_id].append("Best overall")
        badges[fastest.route.route_id].append("Fastest")
        complete = [o for o in ranked if o.complete_cost]
        if complete:  # no "Cheapest" claim at all when every total is partial
            cheapest = min(complete, key=keys["cheapest"])
            badges[cheapest.route.route_id].append("Cheapest")
        drive = next((o for o in ranked if o.route.route_id == "drive"), None)
        for o in ranked:
            r = o.route
            r.label = " · ".join(badges[r.route_id]) or None
            if drive is None or o is drive:
                text = f"{r.total_minutes:.0f} min door to door for ${o.known_cost:.2f}."
                daily = _total(r.round_trip.daily_cost_breakdown) if r.round_trip else None
                if r.round_trip and daily and daily.amount is not None:
                    text += f" Round trip: ${daily.amount:.2f} a day"
                    if r.round_trip.monthly_cost.amount is not None:
                        text += f", ${r.round_trip.monthly_cost.amount:,.0f} a month"
                    text += "."
            else:
                saved = drive.known_cost - o.known_cost
                extra = r.total_minutes - drive.route.total_minutes
                money = f"saves ${saved:.2f}" if saved >= 0 else f"costs ${-saved:.2f} more"
                time = f"{abs(extra):.0f} min {'longer' if extra >= 0 else 'faster'}"
                text = f"Versus driving all the way: {money} and is {time}."
                savings = r.round_trip.savings_vs_drive if r.round_trip else None
                if savings and savings.daily.amount is not None:
                    per_day = savings.daily.amount
                    text += (
                        f" Round trip: saves ${per_day:.2f} a day"
                        if per_day >= 0
                        else f" Round trip: costs ${-per_day:.2f} more a day"
                    )
                    if savings.monthly.amount is not None:
                        text += f", ${abs(savings.monthly.amount):,.0f} a month"
                    text += "."
            if not o.complete_cost:
                text += (
                    " Some costs are unknown (see warnings), so it ranks after options whose"
                    " costs are all known."
                )
            r.explanation = Explanation(text=text, provenance=Provenance.ESTIMATED)

    def _disclaimers(self) -> list[str]:
        vehicle = self._vehicle()
        return [
            "Train times are NJ TRANSIT's published schedule, not real-time.",
            "Drive times are free-flow estimates from OpenStreetMap data "
            "(© OpenStreetMap contributors); they ignore live traffic.",
            f"Driving cost is {vehicle.cost_scope[0].lower()}{vehicle.cost_scope[1:]}",
            "Park-and-ride parking assumes the car stays "
            f"{self._corridor.assumed_parking_hours:g} hours.",
            "Tolls assume E-ZPass unless cash is selected; "
            "NJ Turnpike off-peak rates require a New Jersey E-ZPass.",
            "Prices come from agency sources dated in the data files; verify before you travel.",
            "Daily round trip: the trip home leaves at the return time; parking and the congestion "
            "toll are charged once a day. Monthly and annual figures assume "
            f"{self._corridor.commute.working_days_per_year} working days a year (estimated) and "
            "do not include monthly garage or lot permits.",
        ]
