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
from app.trips.models import TripSearchRequest
from app.trips.service import Station, TripSearchError, TripSearchService

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
        return DriveRoute(30 * 60, 32000, "", ())


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
    assert routes[0].label and "Cheapest" in routes[0].label


def test_fastest_label_goes_to_the_quickest_option(service: TripSearchService) -> None:
    routes = service.search(request(), NOW).routes
    quickest = min(routes, key=lambda r: r.total_minutes)

    assert quickest.label and "Fastest" in quickest.label


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


def test_unknown_request_fields_are_rejected(app: FastAPI) -> None:
    client = TestClient(app)
    token = client.post("/api/v1/session").json()["session_token"]
    body = {**request().model_dump(mode="json"), "user_id": "spoofed"}  # N-06

    response = client.post("/api/v1/trip/search", json=body, headers={"X-Session-Token": token})

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
