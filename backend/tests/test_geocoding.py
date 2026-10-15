"""Address lookup (item 23): Nominatim adapter policy + resolver acceptance rules (N-04, N-05).

Fake geocoder and fake transport only — no network.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.parsing.places import PlaceResolver, names_agree, towns_agree
from app.parsing.rules import RulesParser
from app.parsing.service import TripParseService
from app.providers.base import GeocodeResult, LatLon, ProviderError
from app.providers.nominatim import ATTRIBUTION, NominatimGeocoder
from app.regions import get_region_config
from app.regions.loader import resolve_region_path
from app.trips.corridor import Corridor, load_corridor
from app.trips.models import Provenance

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 14, 20, 0, tzinfo=TZ)
BOX = (40.0, -75.2, 42.15, -71.8)


def _hit(
    name: str, town: str | None, lat: float, lng: float, kind: str = "amenity"
) -> GeocodeResult:
    return GeocodeResult(
        name=name,
        town=town,
        display_name=f"{name}, {town or ''}, New Jersey",
        point=LatLon(lat, lng),
        kind=kind,
    )


class FakeGeocoder:
    attribution = ATTRIBUTION

    def __init__(self, answers: dict[str, list[GeocodeResult]] | None = None, down: bool = False):
        self.answers = answers or {}
        self.down = down
        self.queries: list[str] = []

    def search(self, query: str) -> list[GeocodeResult]:
        self.queries.append(query)
        if self.down:
            raise ProviderError("address lookup unavailable (ConnectError)")
        return self.answers.get(query.lower(), [])


@pytest.fixture(scope="module")
def corridor() -> Corridor:
    region = get_region_config()
    return load_corridor(resolve_region_path(f"data/regions/{region.region_id}-demo-corridor.yaml"))


def _service(corridor: Corridor, geocoder: FakeGeocoder) -> TripParseService:
    rules = RulesParser()
    return TripParseService(
        parser=rules,
        fallback=rules,
        resolver=PlaceResolver(corridor, geocoder),
        corridor=corridor,
        timezone=TZ,
    )


# -- name / town agreement -----------------------------------------------------------


@pytest.mark.parametrize(
    ("found", "said", "agree"),
    [
        ("DeLucia's Brick Oven Pizza", "DeLucia's Brick Oven Pizza", True),
        ("DeLucia's Brick Oven Pizza", "delucias", True),
        ("Brick Oven Pizza", "DeLucia's Brick Oven Pizza", False),
        ("Napoli's Brick Oven Pizza", "DeLucia's Brick Oven Pizza", False),
        ("429 11th Avenue", "429 11th Ave", True),
        ("431 11th Avenue", "429 11th Ave", False),
    ],
)
def test_names_agree(found: str, said: str, agree: bool) -> None:
    assert names_agree(found, said) is agree


@pytest.mark.parametrize(
    ("found", "said", "agree"),
    [
        ("Raritan", "raritan", True),
        ("Raritan", "Raritan, NJ", True),
        ("Bridgewater Township", "bridgewater", True),
        ("Metuchen", "raritan", False),
        (None, "raritan", False),
    ],
)
def test_towns_agree(found: str | None, said: str, agree: bool) -> None:
    assert towns_agree(found, said) is agree


# -- resolver ------------------------------------------------------------------------


def test_verified_places_come_first_without_a_lookup(corridor: Corridor) -> None:
    geocoder = FakeGeocoder()
    out = _service(corridor, geocoder).parse("from Princeton to the javits center", NOW)

    assert out.missing_fields == []
    assert geocoder.queries == []


def test_name_or_town_mismatch_is_rejected_not_used(corridor: Corridor) -> None:
    """Live fuzzy search for "DeLucia's in Raritan" returned pizzerias in Metuchen/Elizabeth."""
    geocoder = FakeGeocoder(
        {
            "delucia's brick oven pizza, raritan": [
                _hit("Brick Oven Pizza", "Metuchen", 40.5432, -74.3632),
                _hit("DeLucia's Pizza", "Elizabeth", 40.6640, -74.2107),
            ]
        }
    )
    out = _service(corridor, geocoder).parse(
        "from DeLucia's Brick Oven Pizza in Raritan to Times Square", NOW
    )
    raritan = next(p for p in corridor.origins if p.id == "raritan")

    assert out.draft.origin is not None
    assert (out.draft.origin.lat, out.draft.origin.lng) == (raritan.lat, raritan.lng)
    origin = next(i for i in out.interpretation if i.field == "origin")
    assert origin.provenance is Provenance.ESTIMATED
    assert out.clarifying_question and "DeLucia's Brick Oven Pizza" in out.clarifying_question


def test_matching_name_and_town_is_used_with_attribution(corridor: Corridor) -> None:
    geocoder = FakeGeocoder(
        {
            "delucia's brick oven pizza, raritan": [
                _hit("Brick Oven Pizza", "Metuchen", 40.5432, -74.3632),
                _hit("DeLucia's Brick Oven Pizza", "Raritan", 40.5697, -74.6330),
            ]
        }
    )
    out = _service(corridor, geocoder).parse(
        "from DeLucia's Brick Oven Pizza in raritan to the javits center", NOW
    )

    assert out.missing_fields == []
    assert out.draft.origin is not None
    assert (out.draft.origin.lat, out.draft.origin.lng) == (40.5697, -74.6330)
    origin = next(i for i in out.interpretation if i.field == "origin")
    assert origin.provenance is Provenance.AI_GENERATED
    assert "OpenStreetMap" in (origin.note or "")
    assert out.clarifying_question is None


def test_geocoded_destination_reports_zone_and_parking_unknown(corridor: Corridor) -> None:
    geocoder = FakeGeocoder(
        {"55 water st, manhattan": [_hit("55 Water Street", "Manhattan", 40.7034, -74.0110)]}
    )
    out = _service(corridor, geocoder).parse("from Princeton to 55 Water St, Manhattan", NOW)

    dest = next(i for i in out.interpretation if i.field == "destination")
    assert out.draft.destination is not None
    assert "unknown" in (dest.note or "")


def test_unknown_business_in_a_findable_town_uses_the_town_approximately(
    corridor: Corridor,
) -> None:
    geocoder = FakeGeocoder(
        {"hoboken": [_hit("Hoboken", "Hoboken", 40.7440, -74.0324, "boundary")]}
    )
    out = _service(corridor, geocoder).parse("from Joe's Diner in Hoboken to Times Square", NOW)

    assert out.draft.origin is not None and out.draft.origin.lat == 40.7440
    origin = next(i for i in out.interpretation if i.field == "origin")
    assert origin.provenance is Provenance.ESTIMATED
    assert "approximate" in origin.value_label
    assert out.clarifying_question and "Joe's Diner" in out.clarifying_question


def test_lookup_down_falls_back_to_verified_places_with_a_message(corridor: Corridor) -> None:
    out = _service(corridor, FakeGeocoder(down=True)).parse(
        "from DeLucia's Brick Oven Pizza in Raritan to Times Square", NOW
    )

    origin = next(i for i in out.interpretation if i.field == "origin")
    assert origin.provenance is Provenance.ESTIMATED  # Raritan, verified, approximate
    assert "unreachable" in (origin.note or "")


def test_lookup_down_and_no_verified_place_is_missing_with_a_message(corridor: Corridor) -> None:
    out = _service(corridor, FakeGeocoder(down=True)).parse(
        "from Joe's Diner in Hoboken to Times Square", NOW
    )

    assert out.missing_fields == ["origin"]
    origin = next(i for i in out.interpretation if i.field == "origin")
    assert "unreachable" in (origin.note or "")


# -- Nominatim adapter ---------------------------------------------------------------


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _nominatim(
    tmp_path: Path, handler: Callable[[httpx.Request], httpx.Response], clock: _Clock
) -> NominatimGeocoder:
    return NominatimGeocoder(
        cache_dir=tmp_path,
        user_agent="WayBetter-test/1.0 (tests)",
        bounding_box=BOX,
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            headers={"User-Agent": "WayBetter-test/1.0 (tests)"},
        ),
        clock=clock,
        sleep=clock.sleep,
    )


ROW = {
    "lat": "40.5697",
    "lon": "-74.6330",
    "name": "DeLucia's Brick Oven Pizza",
    "category": "amenity",
    "display_name": "DeLucia's Brick Oven Pizza, 3 1st Ave, Raritan, NJ",
    "address": {"house_number": "3", "road": "1st Ave", "town": "Raritan"},
}


def test_nominatim_parses_bounds_and_identifies_itself(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    outside = {**ROW, "lat": "39.0", "name": "Far away"}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[ROW, outside])

    results = _nominatim(tmp_path, handler, _Clock()).search("DeLucia's, Raritan")

    assert [r.name for r in results] == ["DeLucia's Brick Oven Pizza"]
    assert results[0].town == "Raritan"
    params = seen[0].url.params
    assert params["bounded"] == "1" and params["viewbox"] == "-75.2,42.15,-71.8,40.0"
    assert seen[0].headers["User-Agent"].startswith("WayBetter")


def test_nominatim_waits_a_second_between_requests(tmp_path: Path) -> None:
    clock = _Clock()
    geocoder = _nominatim(tmp_path, lambda r: httpx.Response(200, json=[]), clock)

    geocoder.search("first")
    clock.now += 0.25
    geocoder.search("second")

    assert clock.slept == [pytest.approx(0.75)]


def test_nominatim_serves_repeats_from_the_disk_cache(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=[ROW])

    clock = _Clock()
    _nominatim(tmp_path, handler, clock).search("DeLucia's, Raritan")
    again = _nominatim(tmp_path, handler, clock).search("DeLucia's, Raritan")

    assert len(calls) == 1
    assert again[0].name == "DeLucia's Brick Oven Pizza"
    assert list(tmp_path.glob("*.json"))


def test_nominatim_failure_is_a_provider_error(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(ProviderError):
        _nominatim(tmp_path, handler, _Clock()).search("anything")


def test_nominatim_requires_a_user_agent(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        NominatimGeocoder(cache_dir=tmp_path, user_agent=" ", bounding_box=BOX)


def test_address_matches_on_any_locality_and_the_address_line(corridor: Corridor) -> None:
    """Live: 429 11th Ave comes back as the Javits Center, city "New York", suburb "Manhattan"."""
    javits = GeocodeResult(
        name="Jacob K. Javits Convention Center",
        town="New York",
        display_name="Jacob K. Javits Convention Center, 429 11th Avenue, Manhattan, New York",
        point=LatLon(40.7577, -74.0019),
        kind="amenity",
        address_line="429 11th Avenue",
        localities=("Manhattan", "New York"),
    )
    geocoder = FakeGeocoder({"429 11th ave, manhattan": [javits]})
    out = _service(corridor, geocoder).parse("from Princeton to 429 11th Ave, Manhattan", NOW)

    assert out.missing_fields == []
    dest = next(i for i in out.interpretation if i.field == "destination")
    assert dest.provenance is Provenance.AI_GENERATED
    # Within 250 m of the verified Javits Center, so its human-checked facts are used.
    assert dest.value_label == "Javits Center (429 11th Ave)"
    assert out.draft.destination is not None and out.draft.destination.lat == 40.7584


def test_geocoded_address_far_from_verified_places_is_used_as_found(corridor: Corridor) -> None:
    hit = GeocodeResult(
        name="Empire State Building",
        town="New York",
        display_name="Empire State Building, 350 5th Avenue, Manhattan, New York",
        point=LatLon(40.7484, -73.9857),
        kind="tourism",
        address_line="350 5th Avenue",
        localities=("Manhattan", "New York"),
    )
    out = _service(corridor, FakeGeocoder({"350 5th ave, manhattan": [hit]})).parse(
        "from Princeton to 350 5th Ave, Manhattan", NOW
    )

    assert out.draft.destination is not None and out.draft.destination.lat == 40.7484
    dest = next(i for i in out.interpretation if i.field == "destination")
    assert "unknown" in (dest.note or "") and "OpenStreetMap" in (dest.note or "")


def test_a_bare_town_is_its_center_marked_estimated(corridor: Corridor) -> None:
    geocoder = FakeGeocoder(
        {"somerville": [_hit("Somerville", "Somerville", 40.5743, -74.6099, "boundary")]}
    )
    out = _service(corridor, geocoder).parse("from Somerville to Times Square", NOW)

    origin = next(i for i in out.interpretation if i.field == "origin")
    assert origin.provenance is Provenance.ESTIMATED
    assert origin.value_label == "Somerville (town center)"
    assert out.missing_fields == []


def test_a_business_with_no_town_is_not_accepted(corridor: Corridor) -> None:
    geocoder = FakeGeocoder(
        {"empire state building": [_hit("Empire State Building", "New York", 40.7484, -73.9857)]}
    )
    out = _service(corridor, geocoder).parse("from Princeton to the Empire State Building", NOW)

    assert out.missing_fields == ["destination"]
    assert out.clarifying_question and "What town" in out.clarifying_question


# -- typed addresses: state/ZIP, big cities, choices (2026-10-14 live failures) -------------


def _addr(
    name: str,
    road: str | None,
    number: str | None,
    town: str,
    lat: float,
    lng: float,
    kind: str = "place",
    localities: tuple[str, ...] = (),
) -> GeocodeResult:
    line = " ".join(p for p in (number, road) if p) or None
    return GeocodeResult(
        name=name or (line or ""),
        town=town,
        display_name=f"{line}, {town}",
        point=LatLon(lat, lng),
        kind=kind,
        address_line=line,
        road=road,
        localities=localities or (town,),
    )


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ("27 Eddington Ln, Monroe Township, NJ", ["27 Eddington Ln", "Monroe Township"]),
        ("27 Eddington Lane, Monroe Township NJ 08831", ["27 Eddington Lane", "Monroe Township"]),
        ("350 5th Ave, New York, NY", ["350 5th Ave", "New York"]),
        ("Edison, NJ", ["Edison"]),
        ("New Brunswick, New Jersey, USA", ["New Brunswick"]),
    ],
)
def test_address_parts_drop_state_zip_and_country(text: str, parts: list[str]) -> None:
    from app.parsing.places import address_parts

    assert address_parts(text) == parts


def test_a_trailing_state_is_not_mistaken_for_the_town(corridor: Corridor) -> None:
    """Live: "27 Eddington Ln, Monroe Township, NJ" was found by OSM, then rejected because
    "NJ" was compared as the town."""
    house = _addr("", "Eddington Lane", "27", "Monroe Township", 40.2566, -74.4728)
    geocoder = FakeGeocoder({"27 eddington ln, monroe township": [house]})
    out = _service(corridor, geocoder).parse(
        "from 27 Eddington Ln, Monroe Township, NJ to Times Square", NOW
    )

    assert out.missing_fields == []
    assert out.draft.origin is not None and out.draft.origin.lat == 40.2566
    origin = next(i for i in out.interpretation if i.field == "origin")
    assert origin.provenance is Provenance.AI_GENERATED
    assert "town center" not in origin.value_label  # a house is not an area


def test_new_york_as_a_town_still_matches(corridor: Corridor) -> None:
    hit = _addr(
        "Empire State Building", "5th Avenue", "350", "New York", 40.7484, -73.9857,
        kind="tourism", localities=("Manhattan", "New York"),
    )  # fmt: skip
    geocoder = FakeGeocoder({"350 5th ave, new york": [hit]})

    out = _service(corridor, geocoder).parse("from Princeton to 350 5th Ave, New York, NY", NOW)

    assert out.draft.destination is not None and out.draft.destination.lat == 40.7484


def test_a_town_with_its_state_is_the_town_center(corridor: Corridor) -> None:
    town = GeocodeResult(
        name="Monroe Township",
        town="Monroe Township",
        display_name="Monroe Township, Middlesex County, New Jersey",
        point=LatLon(40.3358, -74.4334),
        kind="boundary",
    )
    geocoder = FakeGeocoder({"monroe township": [town]})
    lookup = _service(corridor, geocoder).lookup_place("Monroe Township, New Jersey", "origin")

    assert lookup.place is not None and lookup.place.lat == 40.3358
    assert lookup.value_label == "Monroe Township (town center)"


def test_a_street_in_several_towns_offers_choices_and_picks_none(corridor: Corridor) -> None:
    geocoder = FakeGeocoder(
        {
            "nassau street": [
                _addr(
                    "Nassau Street", "Nassau Street", None, "Princeton", 40.35, -74.65, "highway"
                ),
                _addr("Nassau Street", "Nassau Street", None, "New York", 40.71, -74.01, "highway"),
            ]
        }
    )
    lookup = _service(corridor, geocoder).lookup_place("Nassau Street", "origin")

    assert lookup.place is None
    assert lookup.suggestions == ["Nassau Street, Princeton", "Nassau Street, New York"]
    assert lookup.clarifying_question and "Princeton" in lookup.clarifying_question


def test_plain_words_parse_returns_the_question_with_its_choices(corridor: Corridor) -> None:
    """v0.7.0: /trip/ai-parse sends the same choices as /places/resolve, tagged with the field."""
    geocoder = FakeGeocoder(
        {
            "nassau street": [
                _addr(
                    "Nassau Street", "Nassau Street", None, "Princeton", 40.35, -74.65, "highway"
                ),
                _addr("Nassau Street", "Nassau Street", None, "New York", 40.71, -74.01, "highway"),
            ]
        }
    )
    parse = _service(corridor, geocoder).parse("from Nassau Street to Times Square", NOW)

    assert "origin" in parse.missing_fields
    assert parse.clarifying_question and "Princeton" in parse.clarifying_question
    assert [(c.field, c.text) for c in parse.choices] == [
        ("origin", "Nassau Street, Princeton"),
        ("origin", "Nassau Street, New York"),
    ]


def test_a_name_in_only_one_town_is_used(corridor: Corridor) -> None:
    hit = _addr("Rockefeller Center", None, None, "New York", 40.7593, -73.98, "tourism")
    geocoder = FakeGeocoder({"rockefeller center": [hit]})

    lookup = _service(corridor, geocoder).lookup_place("Rockefeller Center", "destination")

    assert lookup.place is not None and lookup.place.lat == 40.7593


def test_unmatched_house_number_offers_streets_but_uses_the_town_center(
    corridor: Corridor,
) -> None:
    """Live: "75 Main St, Somerville" is 75 East or 75 West Main St. Offer both; pick neither."""
    town = GeocodeResult(
        name="Somerville",
        town="Somerville",
        display_name="Somerville, Somerset County, New Jersey",
        point=LatLon(40.5743, -74.6099),
        kind="boundary",
    )
    geocoder = FakeGeocoder(
        {
            "main st, somerville": [
                _addr("East Main Street", "East Main Street", None, "Somerville", 40.5, -74.6),
                _addr("West Main Street", "West Main Street", None, "Somerville", 40.6, -74.6),
            ],
            "somerville": [town],
        }
    )  # fmt: skip
    lookup = _service(corridor, geocoder).lookup_place("75 Main St, Somerville NJ", "origin")

    assert lookup.place is not None and lookup.place.lat == 40.5743  # town center, approximate
    assert lookup.provenance is Provenance.ESTIMATED
    assert lookup.suggestions == [
        "75 East Main Street, Somerville",
        "75 West Main Street, Somerville",
    ]


def test_number_words_match_digits() -> None:
    assert names_agree("One World Trade Center", "1 World Trade Center")
    assert names_agree("5th Avenue", "Fifth Avenue")
