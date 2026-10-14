"""Trip search: drive-all-the-way vs park-and-ride on one corridor (F-01..F-03 subset).

Flow per request:
  1. Drive all the way: one driving route; fuel + tolls + congestion fee + garage.
  2. Each park-and-ride lot: drive to the lot, park and walk to the platform (region buffer),
     next scheduled train to the hub, then walk or subway to the destination.
  3. Rank, label the winners, and write a one-line explanation from the computed numbers.
All of it is server-side; the client only renders this payload (N-01).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.pricing import DataStatus, PricingData
from app.pricing.models import ParkingLot, VehicleDefaults
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
    RouteLeg,
    RouteOption,
    RouteParking,
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


def _ll(point: LatLon, label: str | None = None) -> LatLng:
    return LatLng(lat=point.lat, lng=point.lon, label=label)


def _minutes(delta: timedelta) -> float:
    return round(delta.total_seconds() / 60, 1)


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
        payment = request.vehicle_profile.toll_payment
        dest_place = self._corridor.place_near(destination)

        options: list[_Option] = []
        warnings_global: list[str] = []
        try:
            options.append(
                self._drive_all_the_way(origin, destination, dest_place, depart, payment)
            )
        except ProviderError as exc:
            warnings_global.append(f"Driving baseline unavailable: {exc}")
        for group in self._pricing.parking_lots:
            for lot in group.lots:
                try:
                    option = self._park_and_ride(
                        lot, origin, destination, dest_place, depart, payment
                    )
                except ProviderError as exc:
                    warnings_global.append(f"{lot.name}: {exc}")
                    continue
                if option:
                    options.append(option)

        ranked = self._rank(options, request.preferences.sort_mode)
        self._label_and_explain(ranked)
        return TripSearchResponse(
            request_id=str(uuid.uuid4()),
            routes=[o.route for o in ranked],
            sort_options=SORT_OPTIONS,
            disclaimers=self._disclaimers() + warnings_global,
        )

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
        )
        return _Option(
            option, breakdown.total, not self._unknown_warnings(breakdown) and not unknown_tolls
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
        fare = self._rail_fare(lot.station)
        transit_fare = fare
        if subway_fare:
            transit_fare = MoneyEstimate(
                amount=None
                if fare.amount is None or subway_fare.amount is None
                else round(fare.amount + subway_fare.amount, 2),
                provenance=costs.worst(fare.provenance, subway_fare.provenance),
                note=f"{fare.note} + {subway_fare.note}",
            )
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
        )
        return _Option(
            option, breakdown.total, not self._unknown_warnings(breakdown) and not unknown_tolls
        )

    def _rail_fare(self, from_station: str) -> MoneyEstimate:
        for table in self._pricing.rail_fares:
            for fare in table.fares:
                if (
                    fare.from_station == from_station
                    and fare.to_station == self._corridor.hub_station
                ):
                    return MoneyEstimate(
                        amount=fare.adult_one_way,
                        provenance=costs.provenance_of(table.status),
                        note=f"{table.agency} one-way, zone {fare.fare_zone}",
                    )
        return MoneyEstimate(
            amount=None, provenance=Provenance.UNKNOWN, note="Rail fare not in data"
        )

    def _last_mile(
        self, hub: Station, destination: LatLon, start: datetime
    ) -> tuple[RouteLeg, MoneyEstimate | None]:
        c = self._corridor
        miles = haversine_m(hub.point, destination) / costs.METERS_PER_MILE * c.walk_detour_factor
        if miles <= c.max_walk_miles:
            end = start + timedelta(hours=miles / c.walk_mph)
            leg = RouteLeg(
                leg_id="walk-2",
                mode="walk",
                start_location=_ll(hub.point, hub.name),
                end_location=_ll(destination),
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
            leg_id="transit-2",
            mode="transit",
            start_location=_ll(hub.point, hub.name),
            end_location=_ll(destination),
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
    def _rank(options: list[_Option], sort_mode: str) -> list[_Option]:
        if not options:
            return []
        min_cost = min((o.known_cost for o in options), default=0) or 1.0
        min_time = min(o.route.total_minutes for o in options) or 1.0

        def score(o: _Option) -> float:
            # Equal weight to money and time, each relative to the best available option.
            return o.known_cost / min_cost + o.route.total_minutes / min_time

        keys = {
            "fastest": lambda o: (o.route.total_minutes, o.known_cost),
            "cheapest": lambda o: (o.known_cost, o.route.total_minutes),
            "best_overall": lambda o: (score(o), o.route.total_minutes),
        }
        return sorted(options, key=keys.get(sort_mode, keys["best_overall"]))

    @staticmethod
    def _label_and_explain(ranked: list[_Option]) -> None:
        if not ranked:
            return
        fastest = min(ranked, key=lambda o: o.route.total_minutes)
        cheapest = min(ranked, key=lambda o: o.known_cost)
        badges: dict[str, list[str]] = {o.route.route_id: [] for o in ranked}
        badges[ranked[0].route.route_id].append("Best overall")
        badges[fastest.route.route_id].append("Fastest")
        badges[cheapest.route.route_id].append("Cheapest")
        drive = next((o for o in ranked if o.route.route_id == "drive"), None)
        for o in ranked:
            r = o.route
            r.label = " · ".join(badges[r.route_id]) or None
            if drive is None or o is drive:
                text = f"{r.total_minutes:.0f} min door to door for ${o.known_cost:.2f}."
            else:
                saved = drive.known_cost - o.known_cost
                extra = r.total_minutes - drive.route.total_minutes
                money = f"saves ${saved:.2f}" if saved >= 0 else f"costs ${-saved:.2f} more"
                time = f"{abs(extra):.0f} min {'longer' if extra >= 0 else 'faster'}"
                text = f"Versus driving all the way: {money} and is {time}."
            if not o.complete_cost:
                text += " Some costs are unknown (see warnings)."
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
        ]
