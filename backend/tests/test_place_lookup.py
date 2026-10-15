"""POST /places/resolve: one typed From/To place, same rules as /trip/ai-parse (F-08, N-02)."""

from __future__ import annotations

from collections.abc import Iterator
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.parsing.factory import get_parse_service
from app.parsing.places import PlaceResolver
from app.parsing.rules import RulesParser
from app.parsing.service import TripParseService
from app.providers.base import GeocodeResult, LatLon
from app.regions import get_region_config
from app.regions.loader import resolve_region_path
from app.trips.corridor import load_corridor
from tests.test_geocoding import FakeGeocoder


@pytest.fixture
def lookup_client(app: FastAPI, client: TestClient) -> Iterator[TestClient]:
    region = get_region_config()
    corridor = load_corridor(
        resolve_region_path(f"data/regions/{region.region_id}-demo-corridor.yaml")
    )
    hit = GeocodeResult(
        name="Empire State Building",
        town="New York",
        display_name="Empire State Building, 350 5th Avenue, Manhattan, New York",
        point=LatLon(40.7484, -73.9857),
        kind="tourism",
        address_line="350 5th Avenue",
        localities=("Manhattan", "New York"),
    )
    rules = RulesParser()
    service = TripParseService(
        parser=rules,
        fallback=rules,
        resolver=PlaceResolver(corridor, FakeGeocoder({"350 5th ave, manhattan": [hit]})),
        corridor=corridor,
        timezone=ZoneInfo(region.timezone),
    )
    app.dependency_overrides[get_parse_service] = lambda: service
    yield client
    app.dependency_overrides.clear()


def _post(client: TestClient, body: dict[str, str], token: bool = True) -> dict[str, object]:
    headers = {}
    if token:
        headers["X-Session-Token"] = client.post("/api/v1/session").json()["session_token"]
    response = client.post("/api/v1/places/resolve", json=body, headers=headers)
    return {"status": response.status_code, **(response.json() if response.content else {})}


def test_requires_a_session(lookup_client: TestClient) -> None:
    out = _post(lookup_client, {"text": "Princeton", "role": "origin"}, token=False)

    assert out["status"] == 401


def test_verified_place(lookup_client: TestClient) -> None:
    out = _post(lookup_client, {"text": "javits", "role": "destination"})

    assert out["status"] == 200
    assert out["value_label"] == "Javits Center (429 11th Ave)"
    assert out["provenance"] == "ai_generated"
    assert out["clarifying_question"] is None


def test_typed_address_via_lookup(lookup_client: TestClient) -> None:
    out = _post(lookup_client, {"text": "350 5th Ave, Manhattan", "role": "destination"})

    assert out["place"] == {
        "lat": 40.7484,
        "lng": -73.9857,
        "label": "Empire State Building, New York",
    }
    assert "OpenStreetMap" in str(out["note"])


def test_business_in_a_known_town_is_approximate_with_a_question(lookup_client: TestClient) -> None:
    out = _post(lookup_client, {"text": "DeLucia's Brick Oven Pizza in Raritan", "role": "origin"})

    assert out["provenance"] == "estimated"
    assert out["clarifying_question"]


def test_not_found_is_null_with_a_question(lookup_client: TestClient) -> None:
    out = _post(lookup_client, {"text": "Atlantis", "role": "origin"})

    assert out["place"] is None
    assert out["provenance"] == "unknown"
    assert out["clarifying_question"]


@pytest.mark.parametrize(
    "body",
    [
        {"text": "", "role": "origin"},
        {"text": "x" * 201, "role": "origin"},
        {"text": "a", "role": "home"},
    ],
)
def test_rejects_bad_input(lookup_client: TestClient, body: dict[str, str]) -> None:
    assert _post(lookup_client, body)["status"] == 422
