"""Trip search: drive-all-the-way vs park-and-ride on one corridor (F-01..F-03 subset).

Flow per request:
  1. Drive all the way: one driving route; fuel + tolls + congestion fee + garage.
  2. Each park-and-ride lot: drive to the lot, park and walk to the platform (region buffer),
     next scheduled train to the hub, then walk or subway to the destination.
  3. The daily commute: each option's evening trip home at the return time, then daily,
     monthly and annual costs (once-a-day charges counted once) and savings versus driving.
  4. Apply the filters (avoid tolls, max walk), listing every hidden option with its reasons.
  5. Rank the rest on the morning trip, badge each unique winner, and explain from the numbers.
All of it is server-side; the client only renders this payload (N-01).
"""

from __future__ import annotations

import itertools
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.pricing import DataStatus, PricingData
from app.pricing.models import EmissionFactors, ParkingLot, RailFares, StationFare, VehicleDefaults
from app.providers.base import DriveRoute, DrivingProvider, LatLon, ProviderError, TransitProvider
from app.providers.polyline import decode
from app.regions.schema import RegionConfig
from app.trips import costs
from app.trips.corridor import Corridor, Place, haversine_m
from app.trips.models import (
    Badge,
    BadgeId,
    CostBreakdown,
    Explanation,
    FilteredRoute,
    LatLng,
    MapLink,
    MoneyEstimate,
    ParkingFacility,
    Preferences,
    Provenance,
    RoundTrip,
    RouteLeg,
    RouteOption,
    RouteParking,
    Savings,
    TripSearchRequest,
    TripSearchResponse,
)

SORT_OPTIONS = [
    "best_overall",
    "fastest",
    "cheapest",
    "least_driving",
    "most_driving",
    "fewest_transfers",
    "cleanest",
]
BADGE_TEXT: dict[BadgeId, str] = {
    "best_overall": "Best overall",
    "fastest": "Fastest",
    "cheapest": "Cheapest",
    "least_driving": "Least driving",
    "fewest_transfers": "Fewest transfers",
    "cleanest": "Cleanest",
}
"""Most driving is a sort tab only: driving the most is not something to award."""


NO_TRIP_HOME = (
    "No trip home planned: the head-home time is not after this departure, so daily, monthly "
    "and yearly costs are unknown."
)


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

    @property
    def co2(self) -> float | None:
        return self.route.emissions_kg.amount


@dataclass(frozen=True)
class _Context:
    """What one request changes about costing: toll payment, fuel inputs, toll avoidance."""

    payment: str
    fuel: costs.Fuel
    avoid_tolls: bool


@dataclass(frozen=True)
class _Drive:
    """A driving route chosen for a leg, with its tolls priced."""

    route: DriveRoute
    tolls: MoneyEstimate
    facilities: set[str]
    unknown_tolls: list[str]
    note: str | None
    """Set when a toll-free alternative replaced the fastest route."""


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


def _polyline_miles(polyline: str | None) -> float | None:
    """Length of an encoded polyline, or None without one (distance then stays unknown)."""
    points = decode(polyline) if polyline else []
    if len(points) < 2:
        return None
    meters = sum(haversine_m(a, b) for a, b in itertools.pairwise(points))
    return round(meters / costs.METERS_PER_MILE, 1)


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
        profile, prefs = request.vehicle_profile, request.preferences
        ctx = _Context(
            payment=profile.toll_payment,
            fuel=costs.fuel_inputs(self._vehicle(), profile.mpg, profile.fuel_price_per_gallon),
            avoid_tolls=prefs.avoid_tolls,
        )
        dest_place = self._corridor.place_near(destination)

        options: list[_Option] = []
        warnings_global: list[str] = []
        if return_at is None:
            warnings_global.append(
                f"The head-home time ({_clock(self._home_time(depart, request.return_time))}) "
                f"is not after the {_clock(depart)} departure, so only the one-way trip is "
                "planned. Set a later head-home time to see daily, monthly and yearly costs."
            )
        try:
            options.append(
                self._drive_all_the_way(origin, destination, dest_place, depart, return_at, ctx)
            )
        except ProviderError as exc:
            warnings_global.append(f"Driving baseline unavailable: {exc}")
        for group in self._pricing.parking_lots:
            for lot in group.lots:
                try:
                    option = self._park_and_ride(
                        lot, origin, destination, dest_place, depart, return_at, ctx
                    )
                except ProviderError as exc:
                    warnings_global.append(f"{lot.name}: {exc}")
                    continue
                if option:
                    options.append(option)

        self._add_savings(options)
        kept, hidden = self._filter(options, prefs)
        ranked = self._rank(kept, prefs.sort_mode)
        self._badge_and_explain(ranked)
        return TripSearchResponse(
            request_id=str(uuid.uuid4()),
            routes=[o.route for o in ranked],
            filtered_out=hidden,
            sort_options=SORT_OPTIONS,
            disclaimers=self._disclaimers() + warnings_global,
        )

    def _home_time(self, depart: datetime, requested: str | None) -> datetime:
        hhmm = requested or self._corridor.commute.default_return_time
        hour, minute = (int(part) for part in hhmm.split(":"))
        return depart.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def _return_at(self, depart: datetime, requested: str | None) -> datetime | None:
        """The head-home time on the departure's day, or None when it is not later than the
        departure (an evening trip): the options are then planned one way only."""
        at = self._home_time(depart, requested)
        return at if at > depart else None

    # -- options -------------------------------------------------------------------

    def _vehicle(self) -> VehicleDefaults:
        return self._pricing.vehicle_defaults[0]

    def _emission_factors(self) -> EmissionFactors | None:
        return self._pricing.emission_factors[0] if self._pricing.emission_factors else None

    def _modes(self, feed_id: str) -> tuple[str, ...]:
        """A feed's transit modes from the region config: what picks its CO2 factor (N-03)."""
        feed = next((f for f in self._region.feeds if f.feed_id == feed_id), None)
        return tuple(m.value for m in feed.modes) if feed else ()

    def _map_links(self, start: LatLon, end: LatLon) -> list[MapLink]:
        return [
            MapLink(
                app_id=h.app_id, label=h.label, url=h.url(start.lat, start.lon, end.lat, end.lon)
            )
            for h in self._region.map_handoff
        ]

    def _drive(
        self, origin: LatLon, destination: LatLon, depart: datetime, ctx: _Context
    ) -> _Drive:
        """The provider's fastest route — or, when avoiding tolls, the first route it offers that
        our toll files price at $0. With none, the fastest stays and the filter hides the option."""
        if not ctx.avoid_tolls:
            route = self._driving.route(origin, destination)
            return _Drive(route, *self._tolls(route, depart, ctx.payment), note=None)
        priced = [
            _Drive(r, *self._tolls(r, depart, ctx.payment), note=None)
            for r in self._driving.route_options(origin, destination)
        ]
        if not priced:
            raise ProviderError("no route")
        fastest = priced[0]
        free = next((d for d in priced if d.tolls.amount == 0 and not d.unknown_tolls), None)
        if free is None or free is fastest:
            return fastest
        extra = (free.route.duration_s - fastest.route.duration_s) / 60
        note = (
            f"Avoiding tolls: a toll-free route ({extra:+.0f} min versus the fastest, which pays "
            f"{_money(fastest.tolls)})"
        )
        return _Drive(free.route, free.tolls, free.facilities, free.unknown_tolls, note)

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
        return_at: datetime | None,
        ctx: _Context,
    ) -> _Option:
        chosen = self._drive(origin, destination, depart, ctx)
        route, tolls, facilities, unknown_tolls = (
            chosen.route,
            chosen.tolls,
            chosen.facilities,
            chosen.unknown_tolls,
        )
        arrive = depart + timedelta(seconds=route.duration_s)
        fuel = costs.fuel_cost(route.distance_m, ctx.fuel)
        zone = costs.zone_toll(
            self._pricing.zone_tolls[0],
            dest_place.in_congestion_relief_zone if dest_place else None,
            arrive,
            facilities,
            ctx.payment,
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
            map_links=self._map_links(origin, destination),
        )
        warnings = self._unknown_warnings(breakdown) + [
            f"Toll not priced: {n}" for n in unknown_tolls
        ]
        if chosen.note:
            warnings.append(chosen.note)
        warnings.append("Drive time is free-flow (no live traffic); rush hour is usually slower.")
        round_trip = None
        if return_at is None:
            warnings.append(NO_TRIP_HOME)
        else:
            try:
                evening = self._drive_home(origin, destination, max(return_at, arrive), ctx)
                round_trip = self._round_trip(evening, breakdown, leg.duration_minutes, None)
                warnings += evening.warnings
            except ProviderError as exc:
                warnings.append(f"Trip home unavailable: {exc}")
        option = RouteOption(
            route_id="drive",
            badges=[],
            summary="Drive all the way",
            total_minutes=leg.duration_minutes,
            drive_minutes=leg.duration_minutes,
            transit_minutes=0,
            walk_minutes=0,
            wait_minutes=0,
            drive_miles=round(miles, 1),
            transfer_count=0,
            cost_breakdown=breakdown,
            emissions_kg=costs.co2_total(
                [costs.car_co2(miles, ctx.fuel, self._emission_factors())]
            ),
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
        self, origin: LatLon, destination: LatLon, leave: datetime, ctx: _Context
    ) -> _Evening:
        chosen = self._drive(destination, origin, leave, ctx)
        route, tolls, unknown_tolls = chosen.route, chosen.tolls, chosen.unknown_tolls
        home = leave + timedelta(seconds=route.duration_s)
        zone = self._pricing.zone_tolls[0]
        evening = _breakdown(
            costs.fuel_cost(route.distance_m, ctx.fuel),
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
            map_links=self._map_links(destination, origin),
        )
        return _Evening(
            summary=f"Leave {_clock(leave)}, drive home, arrive {_clock(home)}",
            legs=[leg],
            costs=evening,
            warnings=self._home_warnings(evening, unknown_tolls)
            + ([f"Trip home: {chosen.note}"] if chosen.note else []),
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
        return_at: datetime | None,
        ctx: _Context,
    ) -> _Option | None:
        station = self._stations.get(lot.station)
        hub = self._stations.get(self._corridor.hub_station)
        if not station or not hub:
            return None
        chosen = self._drive(origin, station.point, depart, ctx)
        drive, tolls, unknown_tolls = chosen.route, chosen.tolls, chosen.unknown_tolls
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
                map_links=self._map_links(origin, station.point),
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
        rail_line = self._transit.trip_polyline(trip)
        legs.append(
            RouteLeg(
                leg_id="transit-1",
                mode="transit",
                start_location=_ll(station.point, station.name),
                end_location=_ll(hub.point, hub.name),
                start_time=trip.departure,
                end_time=trip.arrival,
                duration_minutes=_minutes(trip.arrival - trip.departure),
                distance_miles=_polyline_miles(rail_line),
                agency=trip.agency,
                route_name=trip.route_name,
                headsign=trip.headsign,
                polyline=rail_line,
                time_provenance=Provenance.SCHEDULED,
            )
        )
        last_leg, subway_fare = self._last_mile(hub, destination, trip.arrival)
        legs.append(last_leg)

        fuel = costs.fuel_cost(drive.distance_m, ctx.fuel)
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
        if chosen.note:
            warnings.append(chosen.note)
        if lot.status is DataStatus.ESTIMATED:
            warnings.append(f"{lot.name} price is an estimate: {lot.source.notes or ''}".strip())
        round_trip = None
        if return_at is None:
            warnings.append(NO_TRIP_HOME)
        else:
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
                    ctx,
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
            badges=[],
            summary=f"Park at {station.name.title()}, train to {hub.name.title()}",
            total_minutes=total,
            drive_minutes=legs[0].duration_minutes,
            transit_minutes=round(transit_minutes, 1),
            walk_minutes=round(walk, 1),
            wait_minutes=wait,
            drive_miles=round(drive_miles, 1),
            transfer_count=1 if last_leg.mode == "transit" else 0,
            cost_breakdown=breakdown,
            emissions_kg=self._pnr_co2(legs[0], legs[2], last_leg, ctx),
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
        ctx: _Context,
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
        chosen = self._drive(station.point, origin, at_car, ctx)
        drive, tolls, unknown_tolls = chosen.route, chosen.tolls, chosen.unknown_tolls
        home = at_car + timedelta(seconds=drive.duration_s)
        rail_line = self._transit.trip_polyline(trip)
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
                distance_miles=_polyline_miles(rail_line),
                agency=trip.agency,
                route_name=trip.route_name,
                headsign=trip.headsign,
                polyline=rail_line,
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
                map_links=self._map_links(station.point, origin),
            ),
        ]
        rail = self._rail_fare(lot.station)
        rail = rail.model_copy(update={"note": f"{rail.note}, same fare in reverse"})
        evening = _breakdown(
            costs.fuel_cost(drive.distance_m, ctx.fuel),
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
            warnings=self._home_warnings(evening, unknown_tolls)
            + ([f"Trip home: {chosen.note}"] if chosen.note else []),
        )

    def _pnr_co2(
        self, drive: RouteLeg, rail: RouteLeg, last: RouteLeg, ctx: _Context
    ) -> MoneyEstimate:
        """Drive to the lot, train to the hub, and the subway when the last mile takes it."""
        factors = self._emission_factors()
        parts = [
            costs.car_co2(drive.distance_miles or 0.0, ctx.fuel, factors),
            costs.transit_co2(
                rail.distance_miles, self._modes(self._corridor.transit_feed), "Train", factors
            ),
        ]
        if last.mode == "transit":
            feed = self._pricing.flat_fares[0].feed_id
            parts.append(
                costs.transit_co2(last.distance_miles, self._modes(feed), "Subway", factors)
            )
        return costs.co2_total(parts)

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
    def _filter(
        options: list[_Option], prefs: Preferences
    ) -> tuple[list[_Option], list[FilteredRoute]]:
        """Apply avoid_tolls and max_walk_minutes (F-07). A hidden option is listed with every
        reason it failed, never silently dropped."""
        kept: list[_Option] = []
        hidden: list[FilteredRoute] = []
        for o in options:
            reasons = TripSearchService._filter_reasons(o.route, prefs)
            if reasons:
                hidden.append(
                    FilteredRoute(
                        route_id=o.route.route_id, summary=o.route.summary, reasons=reasons
                    )
                )
            else:
                kept.append(o)
        return kept, hidden

    @staticmethod
    def _filter_reasons(r: RouteOption, prefs: Preferences) -> list[str]:
        reasons: list[str] = []
        if prefs.avoid_tolls:
            trips = [("", r.cost_breakdown)]
            if r.round_trip:
                trips.append(("Trip home: ", r.round_trip.return_cost_breakdown))
            for prefix, c in trips:
                for what, est in (("tolls", c.tolls), ("the congestion toll", c.congestion_fee)):
                    if est.amount is None:
                        reasons.append(f"{prefix}may pay {what}, not priced ({est.note})")
                    elif est.amount > 0:
                        reasons.append(f"{prefix}pays {_money(est)} in {what} ({est.note})")
        limit = prefs.max_walk_minutes
        if limit is not None and r.walk_minutes > limit:
            reasons.append(
                f"Walks {r.walk_minutes:.0f} min on the morning trip; your limit is {limit} min"
            )
        return [reason[0].upper() + reason[1:] for reason in reasons]

    @staticmethod
    def _score(options: list[_Option]) -> Callable[[_Option], float]:
        """Best overall: equal weight to money and time, each relative to the best option (cost
        against complete totals only — a partial total is a lower bound, N-02)."""
        complete = [o for o in options if o.complete_cost] or options
        min_cost = min((o.known_cost for o in complete), default=0) or 1.0
        min_time = min((o.route.total_minutes for o in options), default=0) or 1.0
        return lambda o: o.known_cost / min_cost + o.route.total_minutes / min_time

    @classmethod
    def _rank_keys(
        cls, options: list[_Option]
    ) -> dict[str, Callable[[_Option], tuple[float, ...]]]:
        """Sort keys per mode (F-06). An option with an unknown cost has only a partial total, so
        for cost-based modes it ranks after every option whose total is complete; likewise an
        unknown CO2 ranks last for "cleanest". Time, drive minutes and transfers are always known.
        Ties on a mode's own metric fall back to door-to-door time."""
        score = cls._score(options)

        def partial(o: _Option) -> float:
            return 0.0 if o.complete_cost else 1.0

        def no_co2(o: _Option) -> float:
            return 1.0 if o.co2 is None else 0.0

        return {
            "fastest": lambda o: (o.route.total_minutes, o.known_cost),
            "cheapest": lambda o: (partial(o), o.known_cost, o.route.total_minutes),
            "best_overall": lambda o: (partial(o), score(o), o.route.total_minutes),
            "least_driving": lambda o: (o.route.drive_minutes, o.route.total_minutes),
            "most_driving": lambda o: (-o.route.drive_minutes, o.route.total_minutes),
            "fewest_transfers": lambda o: (o.route.transfer_count, o.route.total_minutes),
            "cleanest": lambda o: (no_co2(o), o.co2 or 0.0, o.route.total_minutes),
        }

    @classmethod
    def _rank(cls, options: list[_Option], sort_mode: str) -> list[_Option]:
        if not options:
            return []
        keys = cls._rank_keys(options)
        return sorted(options, key=keys.get(sort_mode, keys["best_overall"]))

    @staticmethod
    def _unique_winner(pool: list[_Option], metric: Callable[[_Option], float]) -> _Option | None:
        """The one option with the lowest metric, or None when two or more share it (no badge
        on a tie). Metrics are compared at the precision the page shows."""
        if not pool:
            return None
        values = [metric(o) for o in pool]
        best = min(values)
        winners = [o for o, v in zip(pool, values, strict=True) if v == best]
        return winners[0] if len(winners) == 1 else None

    @classmethod
    def _badge_winners(cls, options: list[_Option]) -> dict[BadgeId, _Option]:
        """Who earns each badge. Whole minutes, cents and tenths of a kg are the tie precision;
        cost badges consider complete totals only, "cleanest" known CO2 only."""
        if len(options) < 2:
            return {}  # a badge means "beats the others"; a lone option beats nobody
        score = cls._score(options)
        complete = [o for o in options if o.complete_cost]
        known_co2 = [o for o in options if o.co2 is not None]
        pools: dict[BadgeId, tuple[list[_Option], Callable[[_Option], float]]] = {
            "best_overall": (complete or options, lambda o: round(score(o), 3)),
            "fastest": (options, lambda o: round(o.route.total_minutes)),
            "cheapest": (complete, lambda o: round(o.known_cost, 2)),
            "least_driving": (options, lambda o: round(o.route.drive_minutes)),
            "fewest_transfers": (options, lambda o: o.route.transfer_count),
            "cleanest": (known_co2, lambda o: round(o.co2 or 0.0, 1)),
        }
        winners: dict[BadgeId, _Option] = {}
        for badge, (pool, metric) in pools.items():
            winner = cls._unique_winner(pool, metric)
            if winner is not None:
                winners[badge] = winner
        return winners

    @classmethod
    def _badge_and_explain(cls, ranked: list[_Option]) -> None:
        if not ranked:
            return
        winners = cls._badge_winners(ranked)
        for o in ranked:
            o.route.badges = [
                Badge(id=badge, text=BADGE_TEXT[badge])
                for badge, winner in winners.items()
                if winner is o
            ]
        drive = next((o for o in ranked if o.route.route_id == "drive"), None)
        for o in ranked:
            r = o.route
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
        # The agency comes from the feed registry in region config, never from code (N-03).
        feed = next(
            (f for f in self._region.feeds if f.feed_id == self._corridor.transit_feed), None
        )
        agency = feed.agency_name if feed else "the agency"
        return [
            f"Train times are {agency}'s published schedule, not real-time.",
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
            "CO2 is tailpipe only (EPA factors in the data files): gasoline burned on the drive, "
            "plus national-average rail factors per passenger-mile. Estimates, not measurements.",
            "Google Maps / Apple Maps links hand the drive to that app; its route can differ "
            "from ours.",
        ]
