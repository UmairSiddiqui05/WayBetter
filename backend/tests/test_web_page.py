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
    # Sort tabs render from response.sort_options; ranking stays server-side (N-01). The only place
    # sort ids may appear is LOOK, the icon/colour per server id (presentation), and an id the page
    # doesn't know falls back to a neutral look, so a new server sort needs no page change.
    look = re.search(r"const LOOK = \{.*?\};\n", PAGE, re.S)
    assert look, "LOOK presentation map not found"
    rest = PAGE.replace(look.group(0), "")
    for sort_mode in ("best_overall", "cheapest", "fastest"):
        assert sort_mode not in rest
    assert 'LOOK[id] || { icon: "circle-check", tone: "plain" }' in PAGE
    assert not re.search(r"(current|routes|data\.routes)\.sort\(", PAGE), "the page must not rank"


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


# -- D-21: badges, settings, filters, CO2, map links, Compare (renderer only, N-01) ------------


def test_rows_render_server_badges_not_a_label_string() -> None:
    assert "r.badges" in PAGE
    assert "r.label" not in PAGE  # v0.8.0 removed RouteOption.label


def test_settings_send_vehicle_values_and_filters_in_the_request() -> None:
    for field in ("mpg: settings.mpg", "fuel_price_per_gallon: settings.gas"):
        assert field in PAGE
    for field in ("avoid_tolls: settings.avoidTolls", "max_walk_minutes: settings.walk"):
        assert field in PAGE


def test_vehicle_averages_are_injected_for_the_settings_placeholders(page: str) -> None:
    defaults = presets(page)["vehicle_defaults"]

    assert defaults["mpg"] > 0 and defaults["usd_per_gallon"] > 0


def test_co2_factors_are_listed_as_data_sources(page: str) -> None:
    co2 = [s for s in presets(page)["data_sources"] if s["category"] == "CO2 factor"]

    assert len(co2) >= 3
    assert all(
        s["status"] == "estimated" and s["url"].startswith("https://www.epa.gov") for s in co2
    )


def test_hidden_options_compare_view_and_map_links_render_from_the_response() -> None:
    assert "data.filtered_out" in PAGE and "h.reasons" in PAGE
    assert 'data-view="compare"' in PAGE and "function renderCompare" in PAGE
    assert "leg.map_links" in PAGE and 'rel="noopener noreferrer"' in PAGE
    assert "r.emissions_kg" in PAGE


def test_panel_and_map_share_a_draggable_keyboard_accessible_boundary() -> None:
    assert 'id="splitter" role="separator"' in PAGE and 'aria-orientation="vertical"' in PAGE
    assert 'tabindex="0"' in PAGE  # arrow keys resize too, not only the mouse
    assert "var(--panel-w, 468px)" in PAGE  # the default width when nothing was dragged
    assert ".splitter { display: none; }" in PAGE  # the phone layout stacks instead


# -- D-22: Wayfinding redesign (renderer only, N-01) ----------------------------------------------


def test_cards_are_list_items_with_a_real_button_not_role_button_rows() -> None:
    # axe-core (WCAG 2.1 AA) flagged <li role="button"> inside the <ol>; each card is now a plain
    # list item whose title is a <button> (aria-expanded); "Full details" is a separate button.
    assert 'role="button"' not in PAGE
    assert 'class="c-name" data-sel=' in PAGE and 'aria-expanded="${on}"' in PAGE
    assert 'class="c-open" data-open=' in PAGE


def test_map_markers_have_accessible_names() -> None:
    assert PAGE.count("title: ") >= 4 and "alt: transit.end_location.label" in PAGE


def test_estimates_are_marked_by_a_glyph_with_the_word_kept_for_screen_readers() -> None:
    assert '.st-estimated::before { content: "≈" / "";' in PAGE  # empty alt: the sr text says it
    assert '<span class="sr"> (${esc(provOf(p).word)})</span>' in PAGE


def test_detail_shows_the_parking_facts_the_api_sends() -> None:
    # F-10: lot name, price, capacity, availability confidence, source and date checked.
    for field in ("lot.capacity", "p.confidence", "lot.source_url", "lot.last_verified_at"):
        assert field in PAGE, field
