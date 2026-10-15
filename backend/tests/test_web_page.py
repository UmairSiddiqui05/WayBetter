"""The demo page (D-18): a renderer only (N-01), offline-capable, and every datum labeled (N-02)."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.regions.loader import REPO_ROOT
from app.trips.corridor import load_corridor
from app.trips.factory import get_trip_service
from app.trips.models import Provenance
from app.web.page import STATIC_DIR, TEMPLATE

PAGE = TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture
def page(app: FastAPI) -> str:
    # The page needs only the corridor and timezone; a stub keeps the GTFS archive off CI.
    stub = SimpleNamespace(
        corridor=load_corridor(REPO_ROOT / "data/regions/nyc-metro-demo-corridor.yaml"),
        timezone=ZoneInfo("America/New_York"),
    )
    app.dependency_overrides[get_trip_service] = lambda: stub
    response = TestClient(app).get("/")
    app.dependency_overrides.clear()
    assert response.status_code == 200
    return response.text


def presets(page: str) -> dict:  # type: ignore[type-arg]
    match = re.search(r"const PRESETS = (\{.*?\});\n", page)
    assert match, "presets were not injected"
    return json.loads(match.group(1))


def test_data_sources_are_injected_with_source_date_and_status(page: str) -> None:
    sources = presets(page)["data_sources"]

    assert len(sources) >= 10
    for row in sources:
        assert row["status"] in {p.value for p in Provenance}, row
        assert isinstance(row["human_verified"], bool), row
        assert row["retrieved"], row
        assert row["status"] == "unknown" or row["url"], row  # N-09
    categories = {row["category"] for row in sources}
    assert {"Rail fares", "Tolls", "Station parking", "Gas price", "Working days"} <= categories


def test_template_has_no_money_literals_and_no_hard_coded_sorts() -> None:
    assert not re.search(r"\$\d", PAGE), "a dollar amount is written into the page (F-12)"
    # Sort tabs render from response.sort_options; ranking stays server-side (N-01).
    for sort_mode in ("best_overall", "cheapest", "fastest"):
        assert sort_mode not in PAGE


def test_scripts_fonts_and_icons_load_locally() -> None:
    for url in re.findall(r'<(?:script|link)[^>]+(?:src|href)="([^"]+)"', PAGE):
        assert url.startswith("/static/"), url
    for url in re.findall(r'url\("([^"]+)"\)', PAGE):
        assert url.startswith("/static/"), url
    assert (STATIC_DIR / "fonts" / "OFL.txt").is_file()
    assert (STATIC_DIR / "icons" / "LICENSE").is_file()


def test_vendored_assets_are_served(app: FastAPI) -> None:
    client = TestClient(app)
    for path in (
        "/static/fonts/public-sans-latin-wght-normal.woff2",
        "/static/icons/sprite.svg",
    ):
        assert client.get(path).status_code == 200, path


def test_every_icon_the_page_uses_is_in_the_sprite() -> None:
    sprite = (STATIC_DIR / "icons" / "sprite.svg").read_text(encoding="utf-8")
    symbols = set(re.findall(r'<symbol id="([a-z-]+)"', sprite))
    used = set(re.findall(r'ic\("([a-z-]+)"', PAGE))
    used |= set(re.findall(r'icon: "([a-z-]+)"', PAGE))
    used |= set(re.findall(r'\["([a-z-]+)", "[A-Z][^"]+"\]', PAGE))  # drawer nav entries
    assert used, "no icon references found"
    assert used <= symbols, used - symbols


def test_plain_words_box_posts_to_ai_parse(page: str) -> None:
    # F-08: the page sends the words to the server and renders its interpretation; the parsing,
    # place lookup and defaults all happen server-side (N-01).
    assert 'id="ask-text"' in page
    assert '"/api/v1/trip/ai-parse"' in page
    shown = ("interpretation", "missing_fields", "clarifying_question", "parser_note", "is_default")
    for field in shown:
        assert field in page, field


def test_plain_words_never_search_without_the_user_confirming(page: str) -> None:
    # The reading is shown with a "Show options" button, a Change link per row and the question's
    # choices; reading the words must not start a search by itself.
    assert 'id="ask-show"' in page and "data-ask-change" in page and "data-ask-choice" in page
    reading = page[page.index("async function ask()") : page.index('$("ask-go").addEventListener')]
    assert "search(" not in reading
    assert "fillFromDraft" not in reading
