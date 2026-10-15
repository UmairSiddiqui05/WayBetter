"""Sorts, badges and their tie rules, filters, CO2, the user's own vehicle values and map-app
links (D-21; F-06, F-07, F-14, F-17; N-10 — one test per sort, filter and tie rule)."""

from __future__ import annotations

from typing import get_args

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.pricing import load_pricing_data
from app.providers.base import DriveRoute, DriveStep, LatLon, TransitTrip
from app.providers.polyline import encode
from app.regions import load_region_config
from app.regions.loader import REPO_ROOT
from app.regions.schema import MapHandoff
from app.trips.corridor import load_corridor
from app.trips.factory import get_trip_service
from app.trips.models import BadgeId, Provenance, RouteOption, TripSearchResponse
from app.trips.service import BADGE_TEXT, SORT_OPTIONS, Station, TripSearchService
from tests.test_trip_search import (
    LOTS,
    NOW,
    PENN,
    FakeDriving,
    FakeTransit,
    _opt,
    badges,
    request,
)

METROPARK = LOTS["nyc-metro:njt_rail:metropark"]
TURNPIKE_9_TO_16E = (
    DriveStep("New Jersey Turnpike", "NJTP", "", "merge", LatLon(40.4808, -74.4026), 40000),
    DriveStep("", "", "16E", "off ramp", LatLon(40.7723, -74.0613), 2000),
)


class TollDriving(FakeDriving):
    """FakeDriving, plus: the fastest drive to Metropark uses the Turnpike, and the provider
    also offers a slower toll-free alternative."""

    def _metropark(self, origin: LatLon, destination: LatLon) -> bool:
        return METROPARK in (origin, destination)

    def route(self, origin: LatLon, destination: LatLon) -> DriveRoute:
        if self._metropark(origin, destination):
            return DriveRoute(25 * 60, 42000, "", TURNPIKE_9_TO_16E)
        return super().route(origin, destination)

    def route_options(self, origin: LatLon, destination: LatLon) -> tuple[DriveRoute, ...]:
        fastest = self.route(origin, destination)
        if self._metropark(origin, destination):
            return fastest, DriveRoute(41 * 60, 38000, "", ())
        return (fastest,)


POINTS = {**LOTS, PENN: LatLon(40.7506, -73.9935)}


class ShapedTransit(FakeTransit):
    """FakeTransit with a straight-line shape between the two stations, so rail miles exist."""

    def trip_polyline(self, trip: TransitTrip) -> str | None:
        return encode([POINTS[trip.from_station], POINTS[trip.to_station]])


def _service(driving: FakeDriving, transit: FakeTransit) -> TripSearchService:
    region = load_region_config("data/regions/nyc-metro.yaml")
    stations = {sid: Station(sid, sid.rsplit(":", 1)[1].upper(), p) for sid, p in LOTS.items()}
    stations[PENN] = Station(PENN, "NEW YORK PENN STATION", POINTS[PENN])
    return TripSearchService(
        region=region,
        corridor=load_corridor(REPO_ROOT / "data/regions/nyc-metro-demo-corridor.yaml"),
        pricing=load_pricing_data(region),
        stations=stations,
        driving=driving,
        transit=transit,
    )


@pytest.fixture(scope="module")
def shaped() -> TripSearchService:
    return _service(TollDriving(), ShapedTransit())


@pytest.fixture(scope="module")
def unshaped() -> TripSearchService:
    return _service(FakeDriving(), FakeTransit())


def search(service: TripSearchService, **overrides: object) -> TripSearchResponse:
    return service.search(request(**overrides), NOW)


def by_id(response: TripSearchResponse, route_id: str) -> RouteOption:
    return next(r for r in response.routes if r.route_id == route_id)


# -- sorts (F-06) ------------------------------------------------------------------------


def test_every_sort_is_offered(shaped: TripSearchService) -> None:
    assert search(shaped).sort_options == SORT_OPTIONS
    assert {"least_driving", "most_driving", "fewest_transfers", "cleanest"} <= set(SORT_OPTIONS)


def test_most_driving_puts_the_most_minutes_behind_the_wheel_first() -> None:
    drive = _opt("drive", 40.0, 63, complete=True, drive=63)
    metro = _opt("pnr-metropark", 29.4, 111, complete=True, drive=40)
    near = _opt("pnr-near", 31.0, 105, complete=True, drive=12)

    ranked = TripSearchService._rank([near, metro, drive], "most_driving")

    assert [o.route.route_id for o in ranked] == ["drive", "pnr-metropark", "pnr-near"]


def test_fewest_transfers_then_door_to_door_time() -> None:
    subway = _opt("subway", 20.0, 90, complete=True, transfers=1)
    slow_walk = _opt("slow", 20.0, 100, complete=True, transfers=0)
    quick_walk = _opt("quick", 20.0, 95, complete=True, transfers=0)

    ranked = TripSearchService._rank([subway, slow_walk, quick_walk], "fewest_transfers")

    assert [o.route.route_id for o in ranked] == ["quick", "slow", "subway"]


def test_cleanest_ranks_by_co2_and_an_unknown_co2_last() -> None:
    unknown = _opt("unknown", 20.0, 80, complete=True, co2=None)
    dirty = _opt("dirty", 20.0, 80, complete=True, co2=9.7)
    clean = _opt("clean", 20.0, 80, complete=True, co2=5.1)

    ranked = TripSearchService._rank([unknown, dirty, clean], "cleanest")

    assert [o.route.route_id for o in ranked] == ["clean", "dirty", "unknown"]


def test_requested_sorts_order_the_live_search(shaped: TripSearchService) -> None:
    most = search(shaped, preferences={"sort_mode": "most_driving"}).routes
    fewest = search(shaped, preferences={"sort_mode": "fewest_transfers"}).routes
    cleanest = search(shaped, preferences={"sort_mode": "cleanest"}).routes

    assert [r.drive_minutes for r in most] == sorted((r.drive_minutes for r in most), reverse=True)
    assert [r.transfer_count for r in fewest] == sorted(r.transfer_count for r in fewest)
    co2 = [r.emissions_kg.amount for r in cleanest]
    assert None not in co2 and co2 == sorted(c for c in co2 if c is not None)


# -- badges and the tie rule ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("badge", "a", "b"),
    [
        # whole minutes: 50.2 and 49.8 both show as 50 min
        ("fastest", {"minutes": 50.2}, {"minutes": 49.8}),
        ("cheapest", {"cost": 25.00}, {"cost": 25.00}),
        ("least_driving", {"drive": 20.4}, {"drive": 19.6}),
        ("fewest_transfers", {"transfers": 0}, {"transfers": 0}),
        ("cleanest", {"co2": 6.0}, {"co2": 6.0}),
        ("best_overall", {}, {}),
    ],
)
def test_a_tie_on_a_badges_metric_awards_no_badge(
    badge: str, a: dict[str, float], b: dict[str, float]
) -> None:
    base = {"cost": 30.0, "minutes": 90.0, "drive": 30.0, "transfers": 1, "co2": 8.0}
    worse = {"cost": 60.0, "minutes": 150.0, "drive": 60.0, "transfers": 2, "co2": 20.0}
    options = [
        _opt("a", **{**base, **a}, complete=True),  # type: ignore[arg-type]
        _opt("b", **{**base, **b}, complete=True),  # type: ignore[arg-type]
        _opt("c", **worse, complete=True),  # type: ignore[arg-type]
    ]

    TripSearchService._badge_and_explain(TripSearchService._rank(options, "best_overall"))

    assert not any(badge in badges(o.route) for o in options)


@pytest.mark.parametrize("badge", ["fastest", "cheapest", "least_driving", "fewest_transfers"])
def test_a_unique_winner_gets_the_badge(badge: str) -> None:
    good = _opt("good", 20.0, 80, complete=True, drive=10, transfers=0, co2=4.0)
    bad = _opt("bad", 30.0, 95, complete=True, drive=40, transfers=1, co2=9.0)

    TripSearchService._badge_and_explain(TripSearchService._rank([bad, good], "best_overall"))

    assert badge in badges(good.route) and badge not in badges(bad.route)


def test_cleanest_needs_a_known_co2_to_win() -> None:
    known = _opt("known", 20.0, 80, complete=True, co2=9.0)
    unknown = _opt("unknown", 20.0, 81, complete=True, co2=None)

    TripSearchService._badge_and_explain([known, unknown])

    assert "cleanest" in badges(known.route) and "cleanest" not in badges(unknown.route)


def test_a_lone_option_gets_no_badge() -> None:
    only = _opt("only", 20.0, 80, complete=True, co2=4.0)

    TripSearchService._badge_and_explain([only])

    assert only.route.badges == []


def test_most_driving_is_a_sort_never_a_badge() -> None:
    assert "most_driving" in SORT_OPTIONS
    assert "most_driving" not in get_args(BadgeId)
    assert set(BADGE_TEXT) == set(get_args(BadgeId))


# -- CO2 (F-14, D-21) ---------------------------------------------------------------------


def test_driving_co2_is_gallons_burned_times_the_epa_factor(shaped: TripSearchService) -> None:
    drive = by_id(search(shaped), "drive")
    factors = load_pricing_data(load_region_config("data/regions/nyc-metro.yaml"))
    gallon = factors.emission_factors[0].gasoline.kg_co2_per_gallon
    mpg = factors.vehicle_defaults[0].fuel_economy.mpg

    assert drive.emissions_kg.amount == pytest.approx(drive.drive_miles / mpg * gallon, abs=0.1)
    assert drive.emissions_kg.provenance is Provenance.ESTIMATED
    assert "kg/gal" in (drive.emissions_kg.note or "")


def test_park_and_ride_co2_adds_the_train_per_passenger_mile(shaped: TripSearchService) -> None:
    pnr = by_id(search(shaped), "pnr-hamilton-deck")
    train = next(leg for leg in pnr.legs if leg.leg_id == "transit-1")

    assert train.distance_miles and train.distance_miles > 40  # Hamilton -> Penn, straight line
    note = pnr.emissions_kg.note or ""
    assert "Drive" in note and "Train" in note and "per passenger-mile" in note
    assert pnr.emissions_kg.amount is not None and pnr.emissions_kg.amount > 0


def test_co2_is_unknown_when_the_rail_distance_is_unknown(unshaped: TripSearchService) -> None:
    out = search(unshaped)
    pnr = [r for r in out.routes if r.route_id != "drive"]

    assert all(r.emissions_kg.amount is None for r in pnr)
    assert all(r.emissions_kg.provenance is Provenance.UNKNOWN for r in pnr)
    assert all("distance ridden unknown" in (r.emissions_kg.note or "") for r in pnr)


# -- the user's own vehicle values (F-14, N-02) ------------------------------------------------


def test_user_mpg_and_gas_price_are_user_reported_and_say_so(shaped: TripSearchService) -> None:
    out = search(shaped, vehicle_profile={"mpg": 40, "fuel_price_per_gallon": 3.5})
    drive = by_id(out, "drive")
    fuel = drive.cost_breakdown.gas_or_ev

    assert fuel.provenance is Provenance.USER_REPORTED
    assert "40 mpg (your value)" in (fuel.note or "")
    assert "$3.500/gal (your value)" in (fuel.note or "")
    assert fuel.amount == pytest.approx(drive.drive_miles / 40 * 3.5, abs=0.02)


def test_a_partial_user_profile_mixes_your_value_with_the_data_average(
    shaped: TripSearchService,
) -> None:
    fuel = by_id(search(shaped, vehicle_profile={"mpg": 40}), "drive").cost_breakdown.gas_or_ev

    assert "40 mpg (your value)" in (fuel.note or "")
    assert fuel.note and fuel.note.count("your value") == 1
    assert fuel.provenance is Provenance.USER_REPORTED  # weakest part: the user's own number


def test_user_mpg_also_drives_the_co2_estimate(shaped: TripSearchService) -> None:
    default = by_id(search(shaped), "drive").emissions_kg
    frugal = by_id(search(shaped, vehicle_profile={"mpg": 51}), "drive").emissions_kg

    assert default.amount and frugal.amount and frugal.amount < default.amount
    assert frugal.provenance is Provenance.USER_REPORTED


@pytest.mark.parametrize(
    "profile", [{"mpg": 0}, {"mpg": -5}, {"fuel_price_per_gallon": 0}, {"mpg": 999}]
)
def test_api_rejects_impossible_vehicle_values(
    app: FastAPI, shaped: TripSearchService, profile: dict[str, float]
) -> None:
    app.dependency_overrides[get_trip_service] = lambda: shaped
    client = TestClient(app)
    token = client.post("/api/v1/session").json()["session_token"]
    body = {**request().model_dump(mode="json"), "vehicle_profile": profile}

    response = client.post("/api/v1/trip/search", json=body, headers={"X-Session-Token": token})

    assert response.status_code == 422
    app.dependency_overrides.clear()


# -- filters (F-07): hidden options are listed with reasons, never silently dropped -------------


def test_no_filters_hide_nothing(shaped: TripSearchService) -> None:
    out = search(shaped)

    assert out.filtered_out == []
    assert len(out.routes) == 1 + len(LOTS)


def test_avoid_tolls_hides_tolled_drives_and_says_why(shaped: TripSearchService) -> None:
    out = search(shaped, preferences={"avoid_tolls": True})
    hidden = {f.route_id: f for f in out.filtered_out}

    assert "drive" in hidden and "drive" not in {r.route_id for r in out.routes}
    reasons = " ".join(hidden["drive"].reasons)
    assert "in tolls" in reasons and "Lincoln Tunnel" in reasons
    assert "congestion toll" in reasons
    assert hidden["drive"].summary == "Drive all the way"
    assert len(out.routes) + len(out.filtered_out) == 1 + len(LOTS)


def test_avoid_tolls_takes_a_toll_free_alternative_when_one_is_offered(
    shaped: TripSearchService,
) -> None:
    tolled = by_id(search(shaped), "pnr-metropark-decks")
    avoided = search(shaped, preferences={"avoid_tolls": True})
    metro = by_id(avoided, "pnr-metropark-decks")

    assert tolled.cost_breakdown.tolls.amount and tolled.cost_breakdown.tolls.amount > 0
    assert metro.cost_breakdown.tolls.amount == 0
    assert metro.drive_minutes > tolled.drive_minutes  # the 41-min alternative, not the 25-min
    assert any(w.startswith("Avoiding tolls: a toll-free route") for w in metro.warnings)


def test_max_walk_hides_long_walks_with_the_minutes(shaped: TripSearchService) -> None:
    open_ = search(shaped)
    pnr_walk = min(r.walk_minutes for r in open_.routes if r.route_id != "drive")
    limit = int(pnr_walk) - 1

    out = search(shaped, preferences={"max_walk_minutes": limit})

    assert [r.route_id for r in out.routes] == ["drive"]  # drives door to door: no walking
    for hidden in out.filtered_out:
        assert any(f"your limit is {limit} min" in reason for reason in hidden.reasons)


def test_when_every_option_is_filtered_the_reasons_still_come_back(
    shaped: TripSearchService,
) -> None:
    out = search(shaped, preferences={"avoid_tolls": True, "max_walk_minutes": 0})

    assert out.routes == []
    assert len(out.filtered_out) == 1 + len(LOTS)
    assert all(f.reasons for f in out.filtered_out)


def test_badges_are_awarded_among_the_options_that_remain(shaped: TripSearchService) -> None:
    out = search(shaped, preferences={"avoid_tolls": True})

    assert not any("fastest" in badges(r) and r.route_id == "drive" for r in out.routes)
    assert any(r.badges for r in out.routes)


# -- map-app handoff links (F-17) -----------------------------------------------------------


def test_car_legs_carry_map_links_built_from_the_region_templates(
    shaped: TripSearchService,
) -> None:
    for route in search(shaped).routes:
        legs = [*route.legs, *(route.round_trip.return_legs if route.round_trip else [])]
        for leg in legs:
            if leg.mode != "car":
                assert leg.map_links == []
                continue
            apps = {link.app_id: link.url for link in leg.map_links}
            assert set(apps) == {"google_maps", "apple_maps"}
            start, end = leg.start_location, leg.end_location
            assert f"origin={start.lat:.5f},{start.lng:.5f}" in apps["google_maps"]
            assert f"destination={end.lat:.5f},{end.lng:.5f}" in apps["google_maps"]
            assert f"daddr={end.lat:.5f},{end.lng:.5f}" in apps["apple_maps"]


def test_map_link_templates_only_take_the_two_ends() -> None:
    with pytest.raises(ValueError, match="url_template may only use"):
        MapHandoff(app_id="x", label="X", url_template="https://x.test/?q={user_id}")
    with pytest.raises(ValueError):
        MapHandoff(app_id="x", label="X", url_template="http://x.test/?a={origin_lat}")


def test_hidden_options_are_explained_on_the_wire(app: FastAPI, shaped: TripSearchService) -> None:
    app.dependency_overrides[get_trip_service] = lambda: shaped
    client = TestClient(app)
    token = client.post("/api/v1/session").json()["session_token"]
    body = request(preferences={"avoid_tolls": True}).model_dump(mode="json")

    data = client.post("/api/v1/trip/search", json=body, headers={"X-Session-Token": token}).json()

    assert data["filtered_out"][0]["reasons"]
    assert all("label" not in r and isinstance(r["badges"], list) for r in data["routes"])
    app.dependency_overrides.clear()
