"""OllamaProvider with a fake transport — no network, no model (F-08, D-11, D-19)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from app.parsing.places import PlaceResolver
from app.parsing.rules import RulesParser
from app.parsing.service import TripParseService
from app.providers.base import ProviderError
from app.providers.ollama import OllamaProvider
from app.regions import get_region_config
from app.regions.loader import resolve_region_path
from app.trips.corridor import load_corridor

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 14, 20, 0, tzinfo=TZ)


def _provider(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaProvider(base_url="http://ollama.test", model="qwen3:8b", client=client)


def _reply(content: str) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})

    return handler


def _service(provider: OllamaProvider) -> TripParseService:
    region = get_region_config()
    corridor = load_corridor(
        resolve_region_path(f"data/regions/{region.region_id}-demo-corridor.yaml")
    )
    return TripParseService(
        parser=provider,
        fallback=RulesParser(),
        resolver=PlaceResolver(corridor),
        corridor=corridor,
        timezone=TZ,
    )


def test_sends_schema_temperature_zero_and_only_the_users_words() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"message": {"content": '{"origin_text": "Princeton"}'}})

    parsed = _provider(handler).parse_trip("from Princeton")

    assert parsed.origin_text == "Princeton"
    assert seen["url"] == "http://ollama.test/api/chat"
    assert seen["model"] == "qwen3:8b"
    assert seen["options"] == {"temperature": 0}
    assert seen["stream"] is False
    schema = seen["format"]
    assert isinstance(schema, dict) and schema["additionalProperties"] is False
    messages = seen["messages"]
    assert isinstance(messages, list) and messages[-1] == {
        "role": "user",
        "content": "from Princeton",
    }
    assert "$" not in json.dumps(messages)  # the model never sees a price


def test_valid_output_is_parsed() -> None:
    content = json.dumps(
        {
            "origin_text": "Raritan",
            "destination_text": "Javits Center",
            "priority": "cheapest",
            "leave_time": "07:15",
            "home_time": "18:00",
            "toll_payment": "cash",
        }
    )
    parsed = _provider(_reply(content)).parse_trip("anything")

    assert parsed.priority == "cheapest" and parsed.home_time == "18:00"


@pytest.mark.parametrize(
    "content",
    [
        "not json at all",
        '{"origin_text": "Raritan", "route": "NJ Turnpike"}',  # unknown field
        '{"leave_time": "7 o\'clock"}',  # fails the HH:MM pattern
        '{"priority": "scenic"}',  # not an allowed value
    ],
)
def test_invalid_output_raises_provider_error(content: str) -> None:
    with pytest.raises(ProviderError):
        _provider(_reply(content)).parse_trip("from Raritan")


def test_timeout_raises_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError, match="timed out"):
        _provider(handler).parse_trip("from Raritan")


def test_not_running_raises_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderError, match="unreachable"):
        _provider(handler).parse_trip("from Raritan")


def test_bad_json_falls_back_to_rules_and_says_so() -> None:
    out = _service(_provider(_reply("{oops"))).parse("from Princeton to Times Square", NOW)

    assert out.parser == "rules"
    assert out.parser_note and "ollama:qwen3:8b" in out.parser_note
    assert out.missing_fields == []


def test_timeout_falls_back_to_rules() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    out = _service(_provider(handler)).parse("from Princeton to Times Square, cheapest", NOW)

    assert out.parser == "rules"
    assert out.draft.preferences.sort_mode == "cheapest"


def test_model_output_used_when_valid() -> None:
    content = json.dumps({"origin_text": "raritan", "destination_text": "javits center"})
    out = _service(_provider(_reply(content))).parse("raritan to javits center please", NOW)

    assert out.parser == "ollama:qwen3:8b"
    assert out.missing_fields == []


def test_place_the_model_invented_is_dropped_not_routed() -> None:
    content = json.dumps({"origin_text": "Princeton", "destination_text": "Times Square"})
    out = _service(_provider(_reply(content))).parse("from Princeton to the office", NOW)

    assert out.parser == "ollama:qwen3:8b"
    assert out.draft.destination is None
    assert "destination" in out.missing_fields
    assert out.parser_note and "destination" in out.parser_note


def test_model_place_not_in_the_words_is_dropped() -> None:
    content = json.dumps({"origin_text": "Princeton", "destination_text": "Times Square"})
    out = _service(_provider(_reply(content))).parse("Princeton, then the office", NOW)

    assert out.draft.destination is None
    assert out.parser_note and "dropped the destination" in out.parser_note


def test_model_values_without_backing_words_are_dropped() -> None:
    """Seen live with qwen3:8b: toll payment and priority filled though never mentioned."""
    content = json.dumps(
        {
            "origin_text": "Lawrenceville",
            "destination_text": "the javits",
            "priority": "fastest",
            "toll_payment": "cash",
        }
    )
    out = _service(_provider(_reply(content))).parse("lawrenceville to the javits", NOW)

    assert out.draft.vehicle_profile.toll_payment == "ezpass"  # the default, marked as one
    assert out.draft.preferences.sort_mode == "best_overall"
    assert out.parser_note and "toll payment" in out.parser_note and "priority" in out.parser_note


def test_exact_times_from_the_text_beat_the_models_times() -> None:
    """Seen live: "leaving 7:15 ... home by 6:30" came back as arrive-by 18:30, no leave time."""
    content = json.dumps(
        {"origin_text": "Princeton", "destination_text": "Bryant Park", "arrive_by_time": "18:30"}
    )
    text = "Princeton to Bryant Park, leaving 7:15, need to be home by 6:30"
    out = _service(_provider(_reply(content))).parse(text, NOW)

    assert out.missing_fields == []
    assert out.draft.target_time == datetime(2026, 10, 15, 7, 15, tzinfo=TZ)
    assert out.draft.return_time == "18:30"
    assert out.parser_note and "arrive-by" in out.parser_note


def test_model_time_kept_when_the_hour_was_typed() -> None:
    content = json.dumps(
        {"origin_text": "Princeton", "destination_text": "Times Square", "leave_time": "06:45"}
    )
    out = _service(_provider(_reply(content))).parse(
        "Princeton to Times Square, out the door quarter to 7... no, 6:45", NOW
    )

    assert out.draft.target_time is not None and out.draft.target_time.hour == 6


def test_model_time_dropped_when_no_such_hour_was_typed() -> None:
    content = json.dumps(
        {"origin_text": "Princeton", "destination_text": "Times Square", "leave_time": "08:00"}
    )
    out = _service(_provider(_reply(content))).parse("Princeton to Times Square early", NOW)

    assert out.draft.target_time is not None
    assert out.draft.target_time.strftime("%H:%M") == "07:00"  # the marked default, not 8:00


def test_model_fastest_is_overridden_when_the_words_say_less_driving() -> None:
    """Live (2026-10-14): qwen3:8b read "minimize time spent driving" as fastest, which ranks
    driving all the way first — the opposite of what the user asked."""
    content = json.dumps(
        {"origin_text": "Princeton", "destination_text": "Javits Center", "priority": "fastest"}
    )
    out = _service(_provider(_reply(content))).parse(
        "I want to go from Princeton to Javits Center and minimize time spent driving", NOW
    )

    assert out.draft.preferences.sort_mode == "least_driving"
    assert out.parser_note and "priority" in out.parser_note
