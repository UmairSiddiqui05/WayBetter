"""Trip search service + API, with fake providers (no network)."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.pricing import load_pricing_data
from app.providers.base import DriveRoute, DriveStep, LatLon, TransitTrip
from app.regions import load_region_config
from app.regions.loader import REPO_ROOT
from app.trips.corridor import load_corridor
from app.trips.factory import get_trip_service
from app.trips.models import (
    MoneyEstimate,
    Provenance,
    RoundTrip,
    RouteOption,
    TripSearchRequest,
    TripSearchResponse,
)
from app.trips.service import Station, TripSearchError, TripSearchService, _Option

NY = ZoneInfo("America/New_York")
PENN = "nyc-metro:njt_rail:new-york-penn-station"
LOTS = {
    "nyc-metro:njt_rail:hamilton": LatLon(40.2553, -74.7041),
    "nyc-metro:njt_rail:princeton-jct": LatLon(40.3163, -74.6238),
    "nyc-metro:njt_rail:metropark": LatLon(40.5686, -74.3294),
    "nyc-metro:njt_rail:secaucus-upper-level": LatLon(40.7612, -74.0758),
}
TIMES_SQUARE = {"lat": 40.7580, "lng": -73.9855}
PRINCETON = {"lat": 40.3500, "lng": -74.6597}


class FakeDriving:
    """Every drive: 30 min, 20 mi, no tolled roads — except straight into Manhattan."""

    def route(self, origin: LatLon, destination: LatLon) -> DriveRoute:
        if destination.lon > -74.0:  # Manhattan
            steps = (
                DriveStep(
                    "New Jersey Turnpike", "NJTP", "", "merge", LatLon(40.4808, -74.4026), 40000
                ),
                DriveStep("", "", "16E", "off ramp", LatLon(40.7723, -74.0613), 2000),
                DriveStep("Lincoln Tunnel", "NJ 495", "", "merge", LatLon(40.7649, -74.0235), 2500),
                DriveStep("10th Avenue", "", "", "turn", LatLon(40.7596, -73.9955), 500),
            )
            return DriveRoute(80 * 60, 45000, "", steps)
        if origin.lon > -74.0:  # home from Manhattan: tunnel westbound, Turnpike 16E -> 9
            steps = (
                DriveStep("Lincoln Tunnel", "NY 495", "", "merge", LatLon(40.7589, -73.9992), 2500),
                DriveStep(
                    "New Jersey Turnpike Eastern Spur",
                    "I 95; NJTP",
                    "",
                    "merge",
                    LatLon(40.7741, -74.0603),
                    40000,
                ),
                DriveStep("", "", "9", "off ramp", LatLon(40.4861, -74.3992), 2000),
                DriveStep("Nassau Street", "NJ 27", "", "turn", LatLon(40.3504, -74.6571), 500),
            )
            return DriveRoute(78 * 60, 45000, "", steps)
        return DriveRoute(30 * 60, 32000, "", ())

    def route_options(self, origin: LatLon, destination: LatLon) -> tuple[DriveRoute, ...]:
        return (self.route(origin, destination),)


class FakeTransit:
    def next_trip(self, from_station: str, to_station: str, depart_after: datetime) -> TransitTrip:
        return TransitTrip(
            "t1",
            "NJ TRANSIT RAIL",
            "Northeast Corridor",
            "NEW YORK PENN STATION",
            from_station,
            to_station,
            depart_after + timedelta(minutes=5),
            depart_after + timedelta(minutes=55),
            None,
        )

    def trip_polyline(self, trip: TransitTrip) -> str | None:
        return None


@pytest.fixture(scope="module")
def service() -> TripSearchService:
    region = load_region_config("data/regions/nyc-metro.yaml")
    stations = {sid: Station(sid, sid.rsplit(":", 1)[1].upper(), p) for sid, p in LOTS.items()}
    stations[PENN] = Station(PENN, "NEW YORK PENN STATION", LatLon(40.7506, -73.9935))
    return TripSearchService(
        region=region,
        corridor=load_corridor(REPO_ROOT / "data/regions/nyc-metro-demo-corridor.yaml"),
        pricing=load_pricing_data(region),
        stations=stations,
        driving=FakeDriving(),
        transit=FakeTransit(),
    )


def request(**overrides: object) -> TripSearchRequest:
    body: dict[str, object] = {
        "origin": PRINCETON,
        "destination": TIMES_SQUARE,
        "time_mode": "leave_at",
        "target_time": "2026-10-15T07:00:00-04:00",
    }
    body.update(overrides)
    return TripSearchRequest.model_validate(body)


NOW = datetime(2026, 10, 14, 20, 0, tzinfo=NY)


def badges(route: RouteOption) -> set[str]:
    return {b.id for b in route.badges}


def test_compares_driving_with_every_park_and_ride_lot(service: TripSearchService) -> None:
    response = service.search(request(), NOW)

    ids = {r.route_id for r in response.routes}
    assert "drive" in ids
    assert len(ids) == 1 + len(LOTS)


def test_drive_all_the_way_carries_turnpike_tunnel_and_zone_costs(
    service: TripSearchService,
) -> None:
    drive = next(r for r in service.search(request(), NOW).routes if r.route_id == "drive")

    c = drive.cost_breakdown
    assert c.tolls.amount and c.tolls.amount > 0
    assert "Turnpike" in (c.tolls.note or "") and "Lincoln Tunnel" in (c.tolls.note or "")
    assert c.congestion_fee.amount and c.congestion_fee.amount > 0
    parts = [c.gas_or_ev, c.parking, c.tolls, c.congestion_fee]
    assert c.total == pytest.approx(sum(p.amount or 0 for p in parts), abs=0.01)


def test_park_and_ride_never_pays_the_congestion_fee(service: TripSearchService) -> None:
    for r in service.search(request(), NOW).routes:
        if r.route_id.startswith("pnr-"):
            assert r.cost_breakdown.congestion_fee.amount == 0


def test_cheapest_sort_orders_by_total_cost(service: TripSearchService) -> None:
    routes = service.search(request(preferences={"sort_mode": "cheapest"}), NOW).routes

    totals = [r.cost_breakdown.total for r in routes]
    assert totals == sorted(totals)
    assert "cheapest" in badges(routes[0])
    assert [b.text for b in routes[0].badges if b.id == "cheapest"] == ["Cheapest"]


def test_badges_go_to_unique_winners_only(service: TripSearchService) -> None:
    """The fakes give every park-and-ride the same 30-min drive: a tie for least driving, so no
    one gets that badge, while driving all the way is the one fastest option."""
    routes = service.search(request(), NOW).routes
    drive = next(r for r in routes if r.route_id == "drive")
    pnr_drives = {round(r.drive_minutes) for r in routes if r.route_id != "drive"}

    assert "fastest" in badges(drive)
    assert len(pnr_drives) == 1
    assert not any("least_driving" in badges(r) for r in routes)
    assert not any("most_driving" in badges(r) for r in routes)  # a sort tab, never a badge


def test_unknown_destination_parking_is_flagged_not_invented(service: TripSearchService) -> None:
    elsewhere = {"lat": 40.7300, "lng": -73.9950}  # not a preset: no parking data, zone unknown
    drive = next(
        r
        for r in service.search(request(destination=elsewhere), NOW).routes
        if r.route_id == "drive"
    )

    assert drive.cost_breakdown.parking.amount is None
    assert drive.cost_breakdown.congestion_fee.amount is None
    assert any("unknown" in w for w in drive.warnings)


def test_outside_the_region_is_rejected_before_any_provider_call(
    service: TripSearchService,
) -> None:
    with pytest.raises(TripSearchError, match="outside"):
        service.search(request(origin={"lat": 39.95, "lng": -75.16}), NOW)  # Philadelphia


def test_every_cost_and_leg_carries_provenance(service: TripSearchService) -> None:
    for r in service.search(request(), NOW).routes:
        for leg in r.legs:
            assert leg.time_provenance
        for part in (r.cost_breakdown.gas_or_ev, r.cost_breakdown.parking, r.cost_breakdown.tolls):
            assert part.provenance


def test_api_requires_a_server_issued_session_token(
    app: FastAPI, service: TripSearchService
) -> None:
    app.dependency_overrides[get_trip_service] = lambda: service
    client = TestClient(app)
    body = request().model_dump(mode="json")

    assert client.post("/api/v1/trip/search", json=body).status_code == 401
    assert (
        client.post(
            "/api/v1/trip/search", json=body, headers={"X-Session-Token": "a.b"}
        ).status_code
        == 401
    )

    token = client.post("/api/v1/session")
    assert token.status_code == 201
    ok = client.post(
        "/api/v1/trip/search", json=body, headers={"X-Session-Token": token.json()["session_token"]}
    )
    assert ok.status_code == 200
    assert ok.json()["routes"]
    app.dependency_overrides.clear()


def test_unknown_request_fields_are_rejected(app: FastAPI, service: TripSearchService) -> None:
    # Fake providers: CI has no GTFS archive (gitignored, needs a portal login to fetch).
    app.dependency_overrides[get_trip_service] = lambda: service
    client = TestClient(app)
    token = client.post("/api/v1/session").json()["session_token"]
    body = {**request().model_dump(mode="json"), "user_id": "spoofed"}  # N-06

    response = client.post("/api/v1/trip/search", json=body, headers={"X-Session-Token": token})
    app.dependency_overrides.clear()

    assert response.status_code == 422


def test_demo_page_is_served_with_presets_but_stays_off_the_contract(
    app: FastAPI, service: TripSearchService
) -> None:
    app.dependency_overrides[get_trip_service] = lambda: service
    page = TestClient(app).get("/")
    app.dependency_overrides.clear()

    assert page.status_code == 200
    assert "Princeton (Nassau St)" in page.text  # injected from the corridor data file
    assert "/*__PRESETS__*/" not in page.text
    assert "/" not in app.openapi()["paths"]


def test_page_assets_are_local_so_the_demo_runs_offline(app: FastAPI) -> None:
    client = TestClient(app)

    for path in (
        "/static/leaflet/leaflet.js",
        "/static/leaflet/leaflet.css",
        "/static/basemap-ny-nj-ct.geojson",
    ):
        assert client.get(path).status_code == 200, path


# -- daily round trip --------------------------------------------------------------------


def by_id(response: TripSearchResponse) -> dict[str, RouteOption]:
    return {r.route_id: r for r in response.routes}


def round_trip(option: RouteOption) -> RoundTrip:
    assert option.round_trip is not None
    return option.round_trip


def test_every_option_gets_a_trip_home_at_the_corridor_default(
    service: TripSearchService,
) -> None:
    default = service.corridor.commute.default_return_time
    for r in service.search(request(), NOW).routes:
        home = round_trip(r)
        assert home.return_legs[0].start_time.strftime("%H:%M") == default
        assert home.daily_minutes == pytest.approx(r.total_minutes + home.return_minutes, abs=0.2)


def test_a_requested_return_time_overrides_the_default(service: TripSearchService) -> None:
    for r in service.search(request(return_time="19:15"), NOW).routes:
        assert round_trip(r).return_legs[0].start_time.strftime("%H:%M") == "19:15"


def test_evening_departure_plans_one_way_and_says_why(service: TripSearchService) -> None:
    # A head-home time that isn't after the departure (6:30 AM home, 7:00 AM out; or any trip
    # leaving after the default 5:30 PM) used to be a 422. Now: one-way options, no round trip,
    # daily/monthly/yearly left unknown, and the reason in the disclaimers and on each option.
    response = service.search(request(return_time="06:30"), NOW)

    assert response.routes, "one-way options are still planned"
    for route in response.routes:
        assert route.round_trip is None
        assert route.cost_breakdown.total > 0
        assert any("No trip home planned" in w for w in route.warnings)
    assert any("head-home time (6:30 AM)" in d for d in response.disclaimers)


def test_evening_departure_ranks_and_badges_on_the_one_way_trip(
    service: TripSearchService,
) -> None:
    routes = service.search(request(return_time="06:30"), NOW).routes

    assert sum(len(r.badges) for r in routes) > 0  # ranking does not need the trip home


def test_drive_home_pays_the_turnpike_but_not_the_tunnel_or_a_second_congestion_toll(
    service: TripSearchService,
) -> None:
    drive = round_trip(by_id(service.search(request(), NOW))["drive"])
    evening = drive.return_cost_breakdown

    assert "16E -> 9" in (evening.tolls.note or "")
    assert "Lincoln" not in (evening.tolls.note or "")  # tolled entering New York only
    assert evening.congestion_fee.amount == 0  # charged once per day
    assert evening.parking.amount == 0  # the garage day rate was paid in the morning


def test_daily_cost_counts_once_a_day_charges_once_and_per_trip_costs_twice(
    service: TripSearchService,
) -> None:
    for r in service.search(request(), NOW).routes:
        morning, home = r.cost_breakdown, round_trip(r)
        evening, daily = home.return_cost_breakdown, home.daily_cost_breakdown
        assert daily.parking.amount == morning.parking.amount
        assert daily.congestion_fee.amount == morning.congestion_fee.amount
        for part in ("gas_or_ev", "transit_fare", "tolls"):
            m, e, d = (getattr(b, part).amount for b in (morning, evening, daily))
            assert d == pytest.approx(m + e, abs=0.01), (r.route_id, part)
        assert daily.total == pytest.approx(morning.total + evening.total, abs=0.01)


def test_rail_fare_is_paid_both_ways(service: TripSearchService) -> None:
    pnr = by_id(service.search(request(), NOW))["pnr-metropark-decks"]
    home = round_trip(pnr)

    assert home.return_cost_breakdown.transit_fare.amount == pnr.cost_breakdown.transit_fare.amount
    assert home.return_legs[1].mode == "transit"


def test_monthly_cost_uses_the_monthly_pass_when_it_beats_tickets(
    service: TripSearchService,
) -> None:
    region = load_region_config("data/regions/nyc-metro.yaml")
    fare = next(
        f
        for t in load_pricing_data(region).rail_fares
        for f in t.fares
        if f.from_station == "nyc-metro:njt_rail:metropark"
    )
    assert fare.monthly_pass is not None
    days = service.corridor.commute.working_days_per_year / 12
    home = round_trip(by_id(service.search(request(), NOW))["pnr-metropark-decks"])

    tickets = home.daily_cost_breakdown.total * days
    with_pass = (
        home.daily_cost_breakdown.total - 2 * fare.adult_one_way
    ) * days + fare.monthly_pass
    assert with_pass < tickets
    assert home.monthly_cost.amount == pytest.approx(with_pass, abs=0.01)
    assert home.annual_cost.amount == pytest.approx(12 * with_pass, abs=0.12)
    assert "monthly pass" in (home.monthly_cost.note or "")
    assert home.monthly_cost.provenance is Provenance.ESTIMATED  # working days are estimated


def test_savings_are_driving_minus_the_option_for_each_period(
    service: TripSearchService,
) -> None:
    routes = by_id(service.search(request(), NOW))
    drive = round_trip(routes["drive"])
    assert drive.savings_vs_drive is None
    for route_id, r in routes.items():
        if route_id == "drive":
            continue
        mine = round_trip(r)
        saved = mine.savings_vs_drive
        assert saved is not None
        assert saved.daily.amount == pytest.approx(
            drive.daily_cost_breakdown.total - mine.daily_cost_breakdown.total, abs=0.01
        )
        assert drive.monthly_cost.amount is not None and mine.monthly_cost.amount is not None
        assert saved.monthly.amount == pytest.approx(
            drive.monthly_cost.amount - mine.monthly_cost.amount, abs=0.01
        )
        assert "a day" in r.explanation.text


def test_unknown_daily_cost_leaves_month_year_and_savings_unknown(
    service: TripSearchService,
) -> None:
    elsewhere = {"lat": 40.7300, "lng": -73.9950}  # no garage price, zone membership unknown
    routes = by_id(service.search(request(destination=elsewhere), NOW))
    drive = round_trip(routes["drive"])

    assert drive.monthly_cost.amount is None
    assert drive.monthly_cost.provenance is Provenance.UNKNOWN
    saved = round_trip(routes["pnr-metropark-decks"]).savings_vs_drive
    assert saved is not None and saved.monthly.amount is None


def test_a_stay_past_the_lots_longest_rate_is_unknown_not_guessed(
    service: TripSearchService,
) -> None:
    secaucus = by_id(service.search(request(return_time="23:30"), NOW))[
        "pnr-secaucus-junction-parkfast"
    ]
    home = round_trip(secaucus)

    assert home.return_cost_breakdown.parking.amount is None  # only a 12 h rate is in data
    assert home.monthly_cost.amount is None


class NoTrainHome(FakeTransit):
    def next_trip(
        self, from_station: str, to_station: str, depart_after: datetime
    ) -> TransitTrip | None:
        return (
            None
            if from_station == PENN
            else super().next_trip(from_station, to_station, depart_after)
        )


def test_no_train_home_means_no_round_trip_and_says_why(service: TripSearchService) -> None:
    region = load_region_config("data/regions/nyc-metro.yaml")
    stations = {sid: Station(sid, sid.rsplit(":", 1)[1].upper(), p) for sid, p in LOTS.items()}
    stations[PENN] = Station(PENN, "NEW YORK PENN STATION", LatLon(40.7506, -73.9935))
    stranded = TripSearchService(
        region=region,
        corridor=service.corridor,
        pricing=load_pricing_data(region),
        stations=stations,
        driving=FakeDriving(),
        transit=NoTrainHome(),
    )
    routes = by_id(stranded.search(request(), NOW))

    assert routes["drive"].round_trip is not None
    pnr = routes["pnr-metropark-decks"]
    assert pnr.round_trip is None
    assert any("No scheduled train" in w for w in pnr.warnings)


def test_api_returns_the_round_trip_and_validates_return_time(
    app: FastAPI, service: TripSearchService
) -> None:
    app.dependency_overrides[get_trip_service] = lambda: service
    client = TestClient(app)
    headers = {"X-Session-Token": client.post("/api/v1/session").json()["session_token"]}
    body = request().model_dump(mode="json")

    ok = client.post("/api/v1/trip/search", json={**body, "return_time": "18:00"}, headers=headers)
    bad = client.post("/api/v1/trip/search", json={**body, "return_time": "25:00"}, headers=headers)
    app.dependency_overrides.clear()

    assert ok.status_code == 200
    assert all(r["round_trip"]["monthly_cost"]["provenance"] for r in ok.json()["routes"])
    assert bad.status_code == 422


# -- ranking with unknown costs (N-02) -------------------------------------------------


def _opt(
    route_id: str,
    cost: float,
    minutes: float,
    complete: bool,
    drive: float | None = None,
    transfers: int = 0,
    co2: float | None = None,
) -> _Option:
    route = RouteOption.model_construct(
        route_id=route_id,
        total_minutes=minutes,
        drive_minutes=minutes if drive is None else drive,
        transfer_count=transfers,
        emissions_kg=MoneyEstimate(
            amount=co2, provenance=Provenance.ESTIMATED if co2 is not None else Provenance.UNKNOWN
        ),
        badges=[],
        round_trip=None,
        explanation=None,
    )
    return _Option(route=route, known_cost=cost, complete_cost=complete)


def test_a_partial_total_never_wins_on_price() -> None:
    """Driving to an unverified destination: parking and congestion unknown, so $24.74 is only
    a lower bound and must not beat a complete $26.18."""
    drive = _opt("drive", 24.74, 67, complete=False)
    metro = _opt("pnr-metropark", 26.18, 110, complete=True, drive=40)
    hamilton = _opt("pnr-hamilton", 34.00, 140, complete=True, drive=20)
    options = [drive, metro, hamilton]

    assert [o.route.route_id for o in TripSearchService._rank(options, "cheapest")] == [
        "pnr-metropark",
        "pnr-hamilton",
        "drive",
    ]
    assert TripSearchService._rank(options, "best_overall")[0] is metro
    assert TripSearchService._rank(options, "fastest")[0] is drive  # time is known

    TripSearchService._badge_and_explain(TripSearchService._rank(options, "best_overall"))
    assert [b.text for b in metro.route.badges] == ["Best overall", "Cheapest"]
    assert badges(drive.route) == {"fastest"}
    assert badges(hamilton.route) == {"least_driving"}
    assert "ranks after options whose costs are all known" in drive.route.explanation.text


def test_no_cheapest_badge_when_every_total_is_partial() -> None:
    a, b = _opt("a", 10.0, 50, complete=False), _opt("b", 12.0, 40, complete=False)

    TripSearchService._badge_and_explain(TripSearchService._rank([a, b], "cheapest"))

    assert "cheapest" not in badges(a.route) | badges(b.route)


def test_search_to_an_unverified_destination_ranks_complete_costs_first(
    service: TripSearchService,
) -> None:
    near_times_square = {"lat": 40.7484, "lng": -73.9857, "label": "Empire State Building"}
    for mode in ("cheapest", "best_overall"):
        routes = service.search(
            request(destination=near_times_square, preferences={"sort_mode": mode}), NOW
        ).routes
        partial = [any(w.startswith("Total excludes") for w in r.warnings) for r in routes]

        assert any(partial) and not all(partial)
        assert partial == sorted(partial)  # every complete total before any partial one
        for r, is_partial in zip(routes, partial, strict=True):
            if is_partial:
                assert not badges(r) & {"cheapest", "best_overall"}


def test_least_driving_ranks_by_minutes_behind_the_wheel() -> None:
    """ "Minimize time spent driving" is not "fastest": driving all the way is quickest door to
    door but has the most driving."""
    drive = _opt("drive", 40.0, 63, complete=True, drive=63)
    metro = _opt("pnr-metropark", 29.4, 111, complete=True, drive=40)
    near = _opt("pnr-new-brunswick", 31.0, 105, complete=True, drive=12)

    ranked = TripSearchService._rank([drive, metro, near], "least_driving")

    assert [o.route.route_id for o in ranked] == ["pnr-new-brunswick", "pnr-metropark", "drive"]
    TripSearchService._badge_and_explain(ranked)
    assert "least_driving" in badges(near.route)
    assert "fastest" in badges(drive.route)


def test_least_driving_is_offered_as_a_sort(service: TripSearchService) -> None:
    out = service.search(request(preferences={"sort_mode": "least_driving"}), NOW)

    assert "least_driving" in out.sort_options
    drives = [r.drive_minutes for r in out.routes]
    assert drives == sorted(drives)


def test_schedule_disclaimer_names_the_agency_from_region_config(
    service: TripSearchService,
) -> None:
    # N-03: no agency names in code; the feed registry in region config supplies it.
    disclaimers = service.search(request(), NOW).disclaimers

    assert "Train times are NJ Transit Rail's published schedule, not real-time." in disclaimers
    assert not any("NJ TRANSIT's published" in d for d in disclaimers)
