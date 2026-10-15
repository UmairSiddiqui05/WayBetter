"""POST /trip/ai-parse: rules parser, interpretation, fallback, contract (F-08, N-02, N-04)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.parsing.factory import get_parse_service
from app.parsing.models import ParsedTrip
from app.parsing.places import PlaceResolver
from app.parsing.rules import RulesParser
from app.parsing.service import TripParseService
from app.providers.base import ProviderError
from app.regions import get_region_config
from app.regions.loader import resolve_region_path
from app.trips.corridor import Corridor, load_corridor
from app.trips.models import Provenance

TZ = ZoneInfo("America/New_York")
# A Wednesday evening: "leave at 7" means Thursday 7 AM.
NOW = datetime(2026, 10, 14, 20, 0, tzinfo=TZ)
DELUCIAS = (
    "I have to get from DeLucia's Brick Oven Pizza in raritan to the javits center, "
    "and i want to get there as cheaply as possible, what are my options"
)


@pytest.fixture(scope="module")
def corridor() -> Corridor:
    region = get_region_config()
    return load_corridor(resolve_region_path(f"data/regions/{region.region_id}-demo-corridor.yaml"))


def _service(corridor: Corridor, parser: object | None = None) -> TripParseService:
    rules = RulesParser()
    return TripParseService(
        parser=parser or rules,  # type: ignore[arg-type]
        fallback=rules,
        resolver=PlaceResolver(corridor),
        corridor=corridor,
        timezone=TZ,
    )


def _items(response: object) -> dict[str, object]:
    return {i.field: i for i in response.interpretation}  # type: ignore[attr-defined]


# -- rules parser ------------------------------------------------------------------


def test_rules_parser_reads_the_delucias_request() -> None:
    parsed = RulesParser().parse_trip(DELUCIAS)

    assert parsed.origin_text == "DeLucia's Brick Oven Pizza in raritan"
    assert parsed.destination_text == "the javits center"
    assert parsed.priority == "cheapest"
    assert parsed.leave_time is None and parsed.arrive_by_time is None


@pytest.mark.parametrize(
    ("text", "field", "expected"),
    [
        ("from Princeton to Times Square, leave at 7", "leave_time", "07:00"),
        ("from Princeton to Times Square leaving at 7:30 am", "leave_time", "07:30"),
        ("Princeton to Bryant Park at 6:45am please", "leave_time", "06:45"),
        ("from Princeton to Times Square, home at 6", "home_time", "18:00"),
        ("from Princeton to Times Square and head home at 7:15 pm", "home_time", "19:15"),
        ("from Princeton to Times Square by 9", "arrive_by_time", "09:00"),
        ("from Princeton to Times Square, need to arrive by 8:30", "arrive_by_time", "08:30"),
    ],
)
def test_rules_parser_times(text: str, field: str, expected: str) -> None:
    assert getattr(RulesParser().parse_trip(text), field) == expected


@pytest.mark.parametrize(
    ("text", "priority"),
    [
        ("cheapest way from Princeton to Times Square", "cheapest"),
        ("I want to save money", "cheapest"),
        ("fastest route please", "fastest"),
        ("something quick", "fastest"),
        ("from Princeton to Times Square", None),
    ],
)
def test_rules_parser_priority(text: str, priority: str | None) -> None:
    assert RulesParser().parse_trip(text).priority == priority


@pytest.mark.parametrize(
    ("text", "toll"),
    [
        ("I pay cash", "cash"),
        ("I don't have an E-ZPass", "cash"),
        ("no ezpass", "cash"),
        ("I have E-ZPass", "ezpass"),
        ("from Princeton to Times Square", None),
    ],
)
def test_rules_parser_toll_payment(text: str, toll: str | None) -> None:
    assert RulesParser().parse_trip(text).toll_payment == toll


@pytest.mark.parametrize(
    ("text", "origin", "destination"),
    [
        ("Princeton to Bryant Park, leaving 7:15", "Princeton", "Bryant Park"),
        ("get me to times square from plainsboro", "plainsboro", "times square"),
        ("I need to get to Times Square", None, None),
        ("from Princeton to 429 11th Ave, Manhattan", "Princeton", "429 11th Ave, Manhattan"),
        ("from Princeton to Times Square, leaving at 7", "Princeton", "Times Square"),
        ("to Bryant Park from 3 1st Ave, Raritan", "3 1st Ave, Raritan", "Bryant Park"),
    ],
)
def test_rules_parser_place_forms(text: str, origin: str | None, destination: str | None) -> None:
    parsed = RulesParser().parse_trip(text)

    assert (parsed.origin_text, parsed.destination_text) == (origin, destination)


def test_parsed_trip_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ParsedTrip.model_validate({"origin_text": "Princeton", "price": 12.5})


# -- interpretation ----------------------------------------------------------------


def test_verified_places_and_words_become_a_complete_draft(corridor: Corridor) -> None:
    out = _service(corridor).parse(
        "from Princeton to Times Square leave at 7:30, home at 6, cheapest, cash", NOW
    )

    assert out.missing_fields == []
    assert out.clarifying_question is None
    assert out.parser == "rules"
    draft = out.draft
    assert draft.origin is not None and draft.origin.label == "Princeton (Nassau St)"
    assert draft.destination is not None and draft.destination.label.startswith("Times Square")
    assert draft.time_mode == "leave_at"
    assert draft.target_time == datetime(2026, 10, 15, 7, 30, tzinfo=TZ)
    assert draft.return_time == "18:00"
    assert draft.preferences.sort_mode == "cheapest"
    assert draft.vehicle_profile.toll_payment == "cash"
    items = _items(out)
    assert all(i.provenance is Provenance.AI_GENERATED for i in items.values())  # type: ignore[attr-defined]
    assert not any(i.is_default for i in items.values())  # type: ignore[attr-defined]


def test_defaults_are_marked_as_defaults(corridor: Corridor) -> None:
    out = _service(corridor).parse("from Princeton to Times Square", NOW)
    items = _items(out)

    for field in ("target_time", "return_time", "preferences.sort_mode"):
        assert items[field].is_default  # type: ignore[attr-defined]
        assert items[field].provenance is Provenance.ESTIMATED  # type: ignore[attr-defined]
    assert out.draft.target_time is not None
    assert out.draft.target_time.strftime("%H:%M") == corridor.commute.default_departure_time
    assert out.draft.return_time is None  # the search applies the corridor default itself


def test_friday_night_leave_time_moves_to_monday(corridor: Corridor) -> None:
    friday_night = datetime(2026, 10, 16, 21, 0, tzinfo=TZ)
    out = _service(corridor).parse("from Princeton to Times Square leave at 7", friday_night)

    assert out.draft.target_time == datetime(2026, 10, 19, 7, 0, tzinfo=TZ)


def test_arrive_by_is_reported_missing_not_guessed(corridor: Corridor) -> None:
    out = _service(corridor).parse("from Princeton to Times Square by 9", NOW)

    assert "target_time" in out.missing_fields
    assert out.draft.target_time is None
    item = _items(out)["target_time"]
    assert item.provenance is Provenance.UNKNOWN  # type: ignore[attr-defined]
    assert "isn't supported" in (item.note or "")  # type: ignore[attr-defined]
    assert out.clarifying_question and "leave" in out.clarifying_question


def test_unknown_place_is_missing_with_a_question(corridor: Corridor) -> None:
    out = _service(corridor).parse("from Atlantis to Times Square", NOW)

    assert out.missing_fields == ["origin"]
    assert out.draft.origin is None
    assert _items(out)["origin"].provenance is Provenance.UNKNOWN  # type: ignore[attr-defined]
    assert out.clarifying_question and "Atlantis" in out.clarifying_question


def test_head_home_before_departure_is_rejected(corridor: Corridor) -> None:
    out = _service(corridor).parse("from Princeton to Times Square leave at 8, home at 7 am", NOW)

    assert "return_time" in out.missing_fields
    assert out.draft.return_time is None


class _BrokenParser:
    name = "ollama:test"

    def parse_trip(self, text: str) -> ParsedTrip:
        raise ProviderError("timed out")


def test_parser_failure_falls_back_to_rules(corridor: Corridor) -> None:
    out = _service(corridor, _BrokenParser()).parse("from Princeton to Times Square", NOW)

    assert out.parser == "rules"
    assert out.parser_note and "ollama:test" in out.parser_note
    assert out.missing_fields == []


# -- endpoint -----------------------------------------------------------------------


@pytest.fixture
def parse_client(app: FastAPI, client: TestClient, corridor: Corridor) -> Iterator[TestClient]:
    app.dependency_overrides[get_parse_service] = lambda: _service(corridor)
    yield client
    app.dependency_overrides.clear()


def _token(client: TestClient) -> str:
    return str(client.post("/api/v1/session").json()["session_token"])


def test_endpoint_requires_a_session(parse_client: TestClient) -> None:
    response = parse_client.post("/api/v1/trip/ai-parse", json={"text": "from Princeton"})

    assert response.status_code == 401


def test_endpoint_returns_a_draft_and_interpretation(parse_client: TestClient) -> None:
    response = parse_client.post(
        "/api/v1/trip/ai-parse",
        json={"text": "from Princeton to Times Square, cheapest"},
        headers={"X-Session-Token": _token(parse_client)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["missing_fields"] == []
    assert body["draft"]["preferences"]["sort_mode"] == "cheapest"
    assert {i["field"] for i in body["interpretation"]} >= {"origin", "destination"}
    assert body["parser"] == "rules"


@pytest.mark.parametrize("text", ["", "x" * 1001])
def test_endpoint_rejects_empty_or_long_text(parse_client: TestClient, text: str) -> None:
    response = parse_client.post(
        "/api/v1/trip/ai-parse",
        json={"text": text},
        headers={"X-Session-Token": _token(parse_client)},
    )

    assert response.status_code == 422


def test_endpoint_rejects_unknown_request_fields(parse_client: TestClient) -> None:
    response = parse_client.post(
        "/api/v1/trip/ai-parse",
        json={"text": "from Princeton", "origin": {"lat": 1, "lng": 2}},
        headers={"X-Session-Token": _token(parse_client)},
    )

    assert response.status_code == 422


# -- verified places, aliases, approximate towns (item 14) ---------------------------


def test_delucias_request_uses_raritan_approximately_and_javits_verified(
    corridor: Corridor,
) -> None:
    out = _service(corridor).parse(DELUCIAS, NOW)
    items = _items(out)

    assert out.missing_fields == []
    assert out.draft.preferences.sort_mode == "cheapest"
    origin = items["origin"]
    assert origin.provenance is Provenance.ESTIMATED  # type: ignore[attr-defined]
    assert "Raritan" in origin.value_label  # type: ignore[attr-defined]
    assert "approximate" in origin.value_label.lower()  # type: ignore[attr-defined]
    raritan = next(p for p in corridor.origins if p.id == "raritan")
    assert out.draft.origin is not None
    assert (out.draft.origin.lat, out.draft.origin.lng) == (raritan.lat, raritan.lng)
    assert out.clarifying_question and "DeLucia's Brick Oven Pizza" in out.clarifying_question
    dest = items["destination"]
    assert dest.provenance is Provenance.AI_GENERATED  # type: ignore[attr-defined]
    assert dest.value_label.startswith("Javits Center")  # type: ignore[attr-defined]
    assert "OpenStreetMap" in (dest.note or "")  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("text", "origin_id", "destination_id"),
    [
        ("from raritan nj to javitz center", "raritan", "javits-center"),
        ("from Princeton to Jacob K. Javits Convention Center.", "princeton", "javits-center"),
        ("from Raritan, NJ to the Javits", "raritan", "javits-center"),
        ("from PRINCETON to times square", "princeton", "times-square"),
    ],
)
def test_aliases_and_small_typos_match_verified_places(
    corridor: Corridor, text: str, origin_id: str, destination_id: str
) -> None:
    out = _service(corridor).parse(text, NOW)
    by_id = {p.label: p.id for p in (*corridor.origins, *corridor.destinations)}

    assert out.missing_fields == []
    assert out.draft.origin is not None and out.draft.destination is not None
    assert by_id[out.draft.origin.label or ""] == origin_id
    assert by_id[out.draft.destination.label or ""] == destination_id


def test_unknown_business_in_an_unknown_town_is_not_guessed(corridor: Corridor) -> None:
    out = _service(corridor).parse("from Joe's Diner in Hoboken to Times Square", NOW)

    assert out.missing_fields == ["origin"]
    assert out.draft.origin is None


def test_new_corridor_places_carry_sources_and_honest_unknowns(corridor: Corridor) -> None:
    raritan = next(p for p in corridor.origins if p.id == "raritan")
    javits = next(p for p in corridor.destinations if p.id == "javits-center")

    assert raritan.source and "ODbL" in raritan.source
    assert javits.source and "ODbL" in javits.source
    assert javits.in_congestion_relief_zone is True  # human-confirmed 2026-10-14
    assert javits.parking_area is None  # unknown: no sourced garage rate
