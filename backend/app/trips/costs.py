"""Cost rules. Pure functions over price data + a driving route — no I/O, no literals.

Every amount comes from a data file (F-12, F-13, F-14); these functions only decide
*which* rate applies and say so in the note, so each number on screen is explainable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.pricing.models import (
    BarrierToll,
    CrossingToll,
    DataStatus,
    PeakWindows,
    TicketToll,
    VehicleDefaults,
    ZoneToll,
)
from app.providers.base import DriveRoute, LatLon
from app.trips.corridor import haversine_m
from app.trips.models import MoneyEstimate, Provenance

METERS_PER_MILE = 1609.344
INTERCHANGE_SNAP_M = 3000.0


def provenance_of(status: DataStatus) -> Provenance:
    return Provenance(status.value)


def worst(*values: Provenance) -> Provenance:
    """Unknown beats estimated beats scheduled: a sum is only as good as its weakest part."""
    order = [Provenance.UNKNOWN, Provenance.ESTIMATED, Provenance.SCHEDULED]
    return next((p for p in order if p in values), Provenance.SCHEDULED)


def in_peak(at: datetime, windows: PeakWindows) -> bool:
    spans = windows.weekend if at.weekday() >= 5 else windows.weekday
    hhmm = at.strftime("%H:%M")
    return any(start <= hhmm < end for start, end in spans)


def fuel_cost(distance_m: float, vehicle: VehicleDefaults) -> MoneyEstimate:
    miles = distance_m / METERS_PER_MILE
    gallons = miles / vehicle.fuel_economy.mpg
    price = vehicle.gasoline.usd_per_gallon
    return MoneyEstimate(
        amount=round(gallons * price, 2),
        provenance=worst(
            provenance_of(vehicle.gasoline.status), provenance_of(vehicle.fuel_economy.status)
        ),
        note=f"{miles:.1f} mi at {vehicle.fuel_economy.mpg:g} mpg x ${price:.3f}/gal",
    )


def _time_at_step(route: DriveRoute, index: int, depart: datetime) -> datetime:
    """When the car reaches step `index`, assuming even speed along the route."""
    covered = sum(step.distance_m for step in route.steps[:index])
    fraction = covered / route.distance_m if route.distance_m else 0.0
    return depart + timedelta(seconds=route.duration_s * fraction)


@dataclass(frozen=True)
class TollLine:
    facility_id: str
    amount: float | None
    provenance: Provenance
    note: str


def ticket_toll(
    route: DriveRoute, toll: TicketToll, depart: datetime, payment: str
) -> TollLine | None:
    """Entry/exit-priced road (NJ Turnpike). None when the route never uses it."""
    on_road = [i for i, s in enumerate(route.steps) if toll.road_ref_match in s.ref]
    if not on_road:
        return None
    first = on_road[0]
    entry = _snap(route.steps[first].location, toll)
    exit_ = next((s.exits.split(";")[0].strip() for s in route.steps[first + 1 :] if s.exits), None)
    name = toll.operator
    if not entry or not exit_:
        return TollLine(
            toll.facility_id, None, Provenance.UNKNOWN, f"{name}: interchange not identified"
        )
    rate = toll.rate(entry, exit_)
    if not rate:
        return TollLine(
            toll.facility_id, None, Provenance.UNKNOWN, f"{name} {entry}->{exit_}: rate not in data"
        )
    entered = _time_at_step(route, first, depart)
    peak = in_peak(entered, toll.peak_windows)
    if payment == "cash":
        amount, which = rate.cash, "cash"
    elif peak:
        amount, which = rate.ezpass_peak, "E-ZPass peak"
    else:
        amount, which = rate.nj_ezpass_off_peak, "NJ E-ZPass off-peak"
    return TollLine(
        toll.facility_id,
        amount,
        provenance_of(toll.status),
        f"NJ Turnpike exit {entry} -> {exit_}, {which} (entered {entered:%H:%M})",
    )


def _snap(point: LatLon, toll: TicketToll) -> str | None:
    best = min(
        toll.interchanges,
        key=lambda ic: haversine_m(point, LatLon(ic.lat, ic.lon)),
        default=None,
    )
    if best and haversine_m(point, LatLon(best.lat, best.lon)) <= INTERCHANGE_SNAP_M:
        return best.id
    return None


def barrier_toll(
    route: DriveRoute, toll: BarrierToll, depart: datetime, payment: str
) -> TollLine | None:
    """Open road with barrier plazas (Garden State Parkway): pay each plaza passed in its tolled
    direction. None when the route never uses the road; unknown outside the covered span."""
    on_road = [
        i
        for i, s in enumerate(route.steps)
        if toll.road_match in s.name or toll.road_match in s.ref
    ]
    if not on_road:
        return None
    first = on_road[0]
    point = route.steps[first].location
    entry = min(
        toll.interchanges,
        key=lambda ic: haversine_m(point, LatLon(ic.lat, ic.lon)),
        default=None,
    )
    if entry and haversine_m(point, LatLon(entry.lat, entry.lon)) > INTERCHANGE_SNAP_M:
        entry = None
    label = next((s.exits for s in route.steps[first + 1 :] if s.exits), "")
    number = re.match(r"\d+(\.\d+)?", label)
    name = toll.road_match
    lo, hi = toll.covered_mileposts
    if not entry or not number:
        return TollLine(
            toll.facility_id, None, Provenance.UNKNOWN, f"{name}: interchange not identified"
        )
    exit_mp = float(number.group())
    if not (lo <= entry.milepost <= hi and lo <= exit_mp <= hi):
        return TollLine(
            toll.facility_id,
            None,
            Provenance.UNKNOWN,
            f"{name} {entry.id} -> {label}: outside the plazas in data",
        )
    direction = "southbound" if exit_mp < entry.milepost else "northbound"
    low, high = sorted((entry.milepost, exit_mp))
    passed = [
        p for p in toll.plazas if low < p.milepost < high and p.direction in (direction, "both")
    ]
    at = _time_at_step(route, first, depart)
    trip = f"{name} {entry.id} -> {label} {direction} ({at:%H:%M})"
    if not passed:
        return TollLine(
            toll.facility_id, 0.0, provenance_of(toll.status), f"{trip}, no toll plaza passed"
        )
    if payment == "cash":
        return TollLine(
            toll.facility_id, None, Provenance.UNKNOWN, f"{trip}: cash rate not in data"
        )
    plazas = ", ".join(p.name for p in passed)
    return TollLine(
        toll.facility_id,
        round(sum(p.ezpass for p in passed), 2),
        provenance_of(toll.status),
        f"{trip}, E-ZPass at {plazas}",
    )


def crossing_toll(
    route: DriveRoute, toll: CrossingToll, depart: datetime, payment: str
) -> TollLine | None:
    """Bridge/tunnel toll (Lincoln Tunnel). None when the route does not cross it, or
    crosses in the untolled direction."""
    index = next((i for i, s in enumerate(route.steps) if s.name in toll.route_match_names), None)
    if index is None:
        return None
    if toll.direction_tolled == "into_new_york":
        after = route.steps[index + 1] if index + 1 < len(route.steps) else None
        # Hudson crossings run west->east into New York: eastbound means longitude grows.
        if after is None or after.location.lon <= route.steps[index].location.lon:
            return None
    at = _time_at_step(route, index, depart)
    peak = in_peak(at, toll.peak_windows)
    if payment == "cash":
        amount, which = toll.rates.toll_by_mail, "Tolls by Mail"
    elif peak:
        amount, which = toll.rates.ezpass_peak, "E-ZPass peak"
    else:
        amount, which = toll.rates.ezpass_off_peak, "E-ZPass off-peak"
    return TollLine(
        toll.facility_id,
        amount,
        provenance_of(toll.status),
        f"{toll.route_match_names[0]} eastbound, {which} ({at:%H:%M})",
    )


def zone_toll(
    toll: ZoneToll,
    enters_zone: bool | None,
    arrive: datetime,
    used_facilities: set[str],
    payment: str,
) -> MoneyEstimate:
    if enters_zone is None:
        return MoneyEstimate(
            amount=None,
            provenance=Provenance.UNKNOWN,
            note="Not known whether this destination is inside the Congestion Relief Zone",
        )
    if not enters_zone:
        return MoneyEstimate(amount=0.0, provenance=Provenance.SCHEDULED, note="Outside the zone")
    if payment == "cash":
        return MoneyEstimate(
            amount=None, provenance=Provenance.UNKNOWN, note="Tolls by Mail rate not in data"
        )
    peak = in_peak(arrive, toll.peak_windows)
    base = toll.rates.ezpass_peak if peak else toll.rates.ezpass_overnight
    credit = 0.0
    credited = used_facilities & set(toll.crossing_credit.qualifying_facilities)
    if peak and credited:
        credit = min(toll.crossing_credit.max_credit_peak, base)
    note = f"Congestion Relief Zone, E-ZPass {'peak' if peak else 'overnight'} ${base:.2f}"
    if credit:
        note += f" minus up to ${credit:.2f} tunnel crossing credit"
    return MoneyEstimate(
        amount=round(base - credit, 2), provenance=provenance_of(toll.status), note=note
    )


def sum_known(*items: MoneyEstimate) -> float:
    return round(sum(i.amount for i in items if i.amount is not None), 2)
