"""Cost rules (F-12, F-13, F-14): which rate applies, and that amounts come from data."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.pricing import PricingData, load_pricing_data
from app.providers.base import DriveRoute, DriveStep, LatLon
from app.regions import load_region_config
from app.trips import costs
from app.trips.models import Provenance

NY = ZoneInfo("America/New_York")
THU_7AM = datetime(2026, 10, 15, 7, 0, tzinfo=NY)  # a weekday
THU_NOON = datetime(2026, 10, 15, 12, 0, tzinfo=NY)


@pytest.fixture(scope="module")
def pricing() -> PricingData:
    return load_pricing_data(load_region_config("data/regions/nyc-metro.yaml"))


def step(
    name: str = "",
    ref: str = "",
    exits: str = "",
    lat: float = 40.0,
    lon: float = -74.5,
    maneuver: str = "turn",
    meters: float = 1000,
) -> DriveStep:
    return DriveStep(name, ref, exits, maneuver, LatLon(lat, lon), meters)


def route(*steps: DriveStep, seconds: float = 3600) -> DriveRoute:
    return DriveRoute(seconds, sum(s.distance_m for s in steps), "", tuple(steps))


def turnpike_to_lincoln() -> DriveRoute:
    """Shape of the real OSRM Princeton -> Times Square route."""
    return route(
        step("Brunswick Pike", "US 1", meters=20000),
        step(
            "New Jersey Turnpike",
            "I 95; NJTP",
            lat=40.4808,
            lon=-74.4026,
            maneuver="merge",
            meters=45000,
        ),
        step(exits="16E", lat=40.7723, lon=-74.0613, maneuver="off ramp", meters=2000),
        step("Lincoln Tunnel", "NJ 495", lat=40.7649, lon=-74.0235, meters=2500),
        step("10th Avenue", lat=40.7596, lon=-73.9955, meters=500),
    )


def test_turnpike_toll_is_looked_up_by_entry_and_exit(pricing: PricingData) -> None:
    toll = pricing.ticket_tolls[0]
    line = costs.ticket_toll(turnpike_to_lincoln(), toll, THU_7AM, "ezpass")

    assert line is not None
    rate = toll.rate("9", "16E")
    assert rate is not None
    assert line.amount == rate.ezpass_peak  # enters ~07:17, inside the 7-9 a.m. peak
    assert "9 -> 16E" in line.note


def test_turnpike_off_peak_rate_applies_midday(pricing: PricingData) -> None:
    toll = pricing.ticket_tolls[0]
    line = costs.ticket_toll(turnpike_to_lincoln(), toll, THU_NOON, "ezpass")

    rate = toll.rate("9", "16E")
    assert line is not None and rate is not None
    assert line.amount == rate.nj_ezpass_off_peak


def test_unlisted_turnpike_pair_is_unknown_not_guessed(pricing: PricingData) -> None:
    odd = route(
        step("New Jersey Turnpike", "NJTP", lat=40.4808, lon=-74.4026, maneuver="merge"),
        step(exits="13A", maneuver="off ramp"),
    )
    line = costs.ticket_toll(odd, pricing.ticket_tolls[0], THU_7AM, "ezpass")

    assert line is not None
    assert line.amount is None and line.provenance is Provenance.UNKNOWN


def test_route_without_turnpike_pays_no_turnpike_toll(pricing: PricingData) -> None:
    local = route(step("Brunswick Pike", "US 1"), step("Lincoln Highway", "NJ 27"))

    assert costs.ticket_toll(local, pricing.ticket_tolls[0], THU_7AM, "ezpass") is None


def test_lincoln_tunnel_is_tolled_eastbound_only(pricing: PricingData) -> None:
    tunnel = pricing.crossing_tolls[0]
    westbound = route(
        step("Lincoln Tunnel", lat=40.7600, lon=-73.9960),
        step("Boulevard East", lat=40.7679, lon=-74.0225),
    )

    eastbound = costs.crossing_toll(turnpike_to_lincoln(), tunnel, THU_7AM, "ezpass")

    assert eastbound is not None and eastbound.amount == tunnel.rates.ezpass_peak
    assert costs.crossing_toll(westbound, tunnel, THU_7AM, "ezpass") is None


def test_congestion_toll_gets_tunnel_credit_at_peak(pricing: PricingData) -> None:
    zone = pricing.zone_tolls[0]
    fee = costs.zone_toll(zone, True, THU_7AM, {"lincoln_tunnel"}, "ezpass")

    expected = zone.rates.ezpass_peak - zone.crossing_credit.max_credit_peak
    assert fee.amount == pytest.approx(expected)


def test_congestion_toll_unknown_when_zone_membership_unknown(pricing: PricingData) -> None:
    fee = costs.zone_toll(pricing.zone_tolls[0], None, THU_7AM, set(), "ezpass")

    assert fee.amount is None and fee.provenance is Provenance.UNKNOWN


def test_overnight_congestion_toll_has_no_credit(pricing: PricingData) -> None:
    zone = pricing.zone_tolls[0]
    late = datetime(2026, 10, 15, 22, 30, tzinfo=NY)

    fee = costs.zone_toll(zone, True, late, {"lincoln_tunnel"}, "ezpass")

    assert fee.amount == zone.rates.ezpass_overnight


def test_fuel_cost_is_miles_over_mpg_times_price(pricing: PricingData) -> None:
    vehicle = pricing.vehicle_defaults[0]
    fee = costs.fuel_cost(costs.METERS_PER_MILE * 51, vehicle)

    expected = 51 / vehicle.fuel_economy.mpg * vehicle.gasoline.usd_per_gallon
    assert fee.amount == pytest.approx(expected, abs=0.01)
    assert fee.provenance is Provenance.ESTIMATED


def test_worst_provenance_wins() -> None:
    assert costs.worst(Provenance.SCHEDULED, Provenance.ESTIMATED) is Provenance.ESTIMATED
    assert costs.worst(Provenance.ESTIMATED, Provenance.UNKNOWN) is Provenance.UNKNOWN


THU_5_30PM = datetime(2026, 10, 15, 17, 30, tzinfo=NY)
THU_8PM = datetime(2026, 10, 15, 20, 0, tzinfo=NY)


def lincoln_home_to_exit(exit_: str) -> DriveRoute:
    """Shape of the real OSRM Times Square -> Princeton route (westbound, evening)."""
    return route(
        step("Lincoln Tunnel", "NY 495", lat=40.7589, lon=-73.9992, maneuver="merge"),
        step(
            "New Jersey Turnpike Eastern Spur",
            "I 95; NJTP",
            lat=40.7741,
            lon=-74.0603,
            maneuver="merge",
            meters=45000,
        ),
        step(exits=exit_, lat=40.4861, lon=-74.3992, maneuver="off ramp"),
        step("Nassau Street", "NJ 27", lat=40.3504, lon=-74.6571, meters=20000),
    )


def test_turnpike_is_charged_on_the_drive_home_too(pricing: PricingData) -> None:
    """F-13: unlike the Lincoln Tunnel, the Turnpike tolls both directions."""
    toll = pricing.ticket_tolls[0]
    evening = costs.ticket_toll(lincoln_home_to_exit("9"), toll, THU_5_30PM, "ezpass")

    rate = toll.rate("16E", "9")
    assert evening is not None and rate is not None
    assert evening.amount == rate.ezpass_peak  # enters ~17:31, inside the 4:30-6:30 p.m. peak
    assert "16E -> 9" in evening.note


def test_turnpike_evening_off_peak_after_the_peak_window(pricing: PricingData) -> None:
    toll = pricing.ticket_tolls[0]
    late = costs.ticket_toll(lincoln_home_to_exit("8A"), toll, THU_8PM, "ezpass")

    rate = toll.rate("16E", "8A")
    assert late is not None and rate is not None
    assert late.amount == rate.nj_ezpass_off_peak


def test_turnpike_return_rates_mirror_the_morning_rates(pricing: PricingData) -> None:
    """The NJTA grid is symmetric; the return rows were read from the same PDF."""
    toll = pricing.ticket_tolls[0]
    for a, b in (("9", "16E"), ("8A", "16E"), ("9", "15X"), ("8A", "15X")):
        there, back = toll.rate(a, b), toll.rate(b, a)
        assert there is not None and back is not None
        prices = ("ezpass_peak", "nj_ezpass_off_peak", "cash")
        assert [getattr(there, k) for k in prices] == [getattr(back, k) for k in prices]


def test_drive_home_through_the_lincoln_tunnel_pays_no_tunnel_toll(pricing: PricingData) -> None:
    tunnel = pricing.crossing_tolls[0]

    assert costs.crossing_toll(lincoln_home_to_exit("9"), tunnel, THU_5_30PM, "ezpass") is None


def metropark_home_on_parkway(exit_: str) -> DriveRoute:
    """Shape of the real OSRM Metropark -> Princeton route: one mile of the Parkway."""
    return route(
        step("Lincoln Highway", "NJ 27", lat=40.5688, lon=-74.3296, maneuver="depart"),
        step(
            "Garden State Parkway",
            "Garden State Parkway",
            lat=40.5706,
            lon=-74.3283,
            maneuver="merge",
        ),
        step(exits=exit_, lat=40.5566, lon=-74.3195, maneuver="off ramp"),
        step("", "US 1", lat=40.5517, lon=-74.3191, meters=30000),
    )


def test_parkway_between_plazas_is_a_sourced_zero(pricing: PricingData) -> None:
    parkway = pricing.barrier_tolls[0]
    line = costs.barrier_toll(metropark_home_on_parkway("130B-A"), parkway, THU_5_30PM, "ezpass")

    assert line is not None
    assert line.amount == 0 and line.provenance is Provenance.SCHEDULED
    assert "no toll plaza passed" in line.note


def test_parkway_beyond_the_plazas_in_data_is_unknown(pricing: PricingData) -> None:
    parkway = pricing.barrier_tolls[0]
    line = costs.barrier_toll(metropark_home_on_parkway("117"), parkway, THU_5_30PM, "ezpass")

    assert line is not None
    assert line.amount is None and line.provenance is Provenance.UNKNOWN


def test_parkway_plaza_passed_in_its_direction_is_charged(pricing: PricingData) -> None:
    parkway = pricing.barrier_tolls[0].model_copy(update={"covered_mileposts": (120.0, 142.5)})
    raritan = next(p for p in parkway.plazas if p.direction == "southbound")
    line = costs.barrier_toll(metropark_home_on_parkway("123"), parkway, THU_5_30PM, "ezpass")

    cash = costs.barrier_toll(metropark_home_on_parkway("123"), parkway, THU_5_30PM, "cash")

    assert line is not None and line.amount == raritan.ezpass
    assert cash is not None and cash.amount is None  # the cash table is not in data
