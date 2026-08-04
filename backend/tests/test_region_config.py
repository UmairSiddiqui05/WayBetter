"""Region config schema and loader (N-03, D-08)."""

from __future__ import annotations

import pytest

from app.regions import RegionConfig, RegionConfigError, load_region_config
from app.regions.loader import REPO_ROOT

NYC_METRO = "data/regions/nyc-metro.yaml"


@pytest.fixture(scope="module")
def nyc() -> RegionConfig:
    return load_region_config(NYC_METRO)


def _minimal(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "region_id": "test-region",
        "name": "Test Region",
        "timezone": "America/New_York",
        "bounding_box": {"min_lat": 40.0, "min_lng": -75.0, "max_lat": 41.0, "max_lng": -73.0},
        "default_parking_buffer_minutes": 7,
        "feeds": [
            {
                "feed_id": "a_feed",
                "agency_name": "A",
                "modes": ["commuter_rail"],
                "url": "https://example.test/a.zip",
                "license": {"name": "Test"},
            }
        ],
        "data_files": {
            "fares_dir": "data/fares",
            "tolls_dir": "data/tolls",
            "parking_dir": "data/parking",
        },
    }
    base.update(overrides)
    return base


# --- The shipped region ------------------------------------------------------


def test_nyc_metro_config_loads(nyc: RegionConfig) -> None:
    assert nyc.region_id == "nyc-metro"
    assert nyc.timezone == "America/New_York"
    assert nyc.default_parking_buffer_minutes == 7


def test_launch_coverage_falls_inside_the_bounding_box(nyc: RegionConfig) -> None:
    """The box gates every request before a paid provider call (N-05, E-04)."""
    inside = {
        "Manhattan (Penn Station)": (40.7500, -73.9930),
        "Princeton Junction NJ": (40.3200, -74.6260),
        "Trenton NJ (NEC southern terminus)": (40.2170, -74.7700),
        "Morristown NJ": (40.7970, -74.4760),
        "Port Jervis NY": (41.3710, -74.6900),
        "Huntington NY": (40.8250, -73.4100),
        "Montauk NY": (41.0360, -71.9540),
        "Stamford CT": (41.0470, -73.5420),
        "New Haven CT": (41.2980, -72.9270),
        "New London CT": (41.3560, -72.0990),
        "Hartford CT": (41.7700, -72.6800),
        "Springfield MA (Hartford Line north end)": (42.1010, -72.5900),
        "Poughkeepsie NY": (41.7070, -73.9370),
        "Wassaic NY": (41.7900, -73.5600),
    }
    for label, (lat, lng) in inside.items():
        assert nyc.bounding_box.contains(lat, lng), f"{label} should be in region"

    outside = {
        # A looser south-west corner swallows Philadelphia, and out-of-region
        # metros inside the box mean real provider spend on unplannable trips.
        "Philadelphia PA": (39.9526, -75.1652),
        "Boston MA": (42.3601, -71.0589),
        "Chicago IL": (41.8781, -87.6298),
        "Washington DC": (38.9072, -77.0369),
    }
    for label, (lat, lng) in outside.items():
        assert not nyc.bounding_box.contains(lat, lng), f"{label} should be out of region"


def test_every_feed_declares_a_licence(nyc: RegionConfig) -> None:
    """N-09: no feed is used without a recorded licence."""
    for feed in nyc.feeds:
        assert feed.license.name


def test_credentialed_feeds_name_env_vars_not_credentials(nyc: RegionConfig) -> None:
    """Credentials come from the environment; the config only names the variables."""
    credentialed = [f for f in nyc.feeds if f.requires_credentials]
    assert credentialed, "NJ Transit feeds should be registered as credential-gated"
    for feed in credentialed:
        assert feed.credential_env
        assert all(var.isupper() for var in feed.credential_env)


def test_blocked_and_disabled_feeds_explain_themselves(nyc: RegionConfig) -> None:
    """A short registry must say why it is short, not just omit feeds."""
    for feed in nyc.feeds:
        if not feed.enabled:
            assert feed.blocked_reason, f"{feed.feed_id} is disabled without a reason"


def test_fetchable_feeds_excludes_blocked_and_credentialed(nyc: RegionConfig) -> None:
    fetchable = {f.feed_id for f in nyc.fetchable_feeds()}

    assert fetchable == {"mta_subway", "mta_lirr", "mta_mnr"}


def test_zone_polygons_are_referenced_by_path_not_inlined(nyc: RegionConfig) -> None:
    """Geometry is data; PostGIS does the intersection (F-07)."""
    assert nyc.city_driving_zones
    for zone in nyc.city_driving_zones:
        assert zone.geojson_path.endswith(".geojson")


def test_config_points_at_fare_and_toll_files_and_carries_no_amounts(nyc: RegionConfig) -> None:
    """F-12/F-13: the config locates priced data; it never states a price."""
    text = (REPO_ROOT / NYC_METRO).read_text(encoding="utf-8")
    assert "$" not in text

    # Walk every key in the parsed config — a price would have to live under one.
    priceish = ("price", "fare_", "_fare", "amount", "cost", "rate", "toll_")

    def keys(node: object) -> list[str]:
        if isinstance(node, dict):
            return [k for k in node] + [k for v in node.values() for k in keys(v)]
        if isinstance(node, list):
            return [k for item in node for k in keys(item)]
        return []

    offenders = [k for k in keys(nyc.model_dump()) if any(p in k.lower() for p in priceish)]
    assert not offenders, f"region config must not carry priced fields: {offenders}"

    # What it *does* carry is directories to look in.
    assert nyc.data_files.fares_dir.startswith("data/")
    assert nyc.data_files.tolls_dir.startswith("data/")


# --- Schema enforcement ------------------------------------------------------


def test_unknown_keys_are_rejected() -> None:
    """A typo in a region file must fail loudly, not be ignored."""
    with pytest.raises(ValueError, match="extra_field"):
        RegionConfig.model_validate(_minimal(extra_field="oops"))


def test_unknown_timezone_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown IANA timezone"):
        RegionConfig.model_validate(_minimal(timezone="America/Nowhere"))


def test_inverted_bounding_box_is_rejected() -> None:
    box = {"min_lat": 41.0, "min_lng": -75.0, "max_lat": 40.0, "max_lng": -73.0}
    with pytest.raises(ValueError, match="min_lat must be less than max_lat"):
        RegionConfig.model_validate(_minimal(bounding_box=box))


def test_duplicate_feed_ids_are_rejected() -> None:
    feed = {
        "feed_id": "dupe",
        "agency_name": "A",
        "modes": ["subway"],
        "url": "https://example.test/a.zip",
        "license": {"name": "Test"},
    }
    with pytest.raises(ValueError, match="feed_id values must be unique"):
        RegionConfig.model_validate(_minimal(feeds=[feed, dict(feed)]))


def test_credentialed_feed_without_env_vars_is_rejected() -> None:
    feed = {
        "feed_id": "needs_key",
        "agency_name": "A",
        "modes": ["subway"],
        "requires_credentials": True,
        "license": {"name": "Test"},
    }
    with pytest.raises(ValueError, match="names no credential_env"):
        RegionConfig.model_validate(_minimal(feeds=[feed]))


def test_enabled_feed_without_a_url_is_rejected() -> None:
    feed = {
        "feed_id": "no_url",
        "agency_name": "A",
        "modes": ["subway"],
        "license": {"name": "Test"},
    }
    with pytest.raises(ValueError, match="enabled but has no url"):
        RegionConfig.model_validate(_minimal(feeds=[feed]))


def test_licence_verification_defaults_to_false() -> None:
    """An agent must never assert that terms permit a use it has not read."""
    config = RegionConfig.model_validate(_minimal())

    assert config.feeds[0].license.verified is False


def test_missing_region_file_raises_a_clear_error() -> None:
    with pytest.raises(RegionConfigError, match="region config not found"):
        load_region_config("data/regions/does-not-exist.yaml")


def test_malformed_region_file_raises_a_clear_error(tmp_path: object) -> None:
    from pathlib import Path

    bad = Path(str(tmp_path)) / "bad.yaml"
    bad.write_text("region_id: 'unclosed\n", encoding="utf-8")

    with pytest.raises(RegionConfigError, match="not valid YAML"):
        load_region_config(bad)
