"""Canonical station identity (N-03).

The headline case is real: in the shipped launch feeds, LIRR `stop_id=1` is
Albertson and Metro-North `stop_id=1` is Grand Central. Raw GTFS stop IDs are
unique only within a feed, so anything outliving one download must key on the
canonical ID instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.ingestion import (
    GtfsStation,
    build_mappings,
    find_duplicate_canonical_ids,
    read_mapping_csv,
    slugify,
    write_mapping_csv,
)

FIXED_TIME = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)

LIRR_STATIONS = [
    GtfsStation("1", "Albertson", 40.77206317, -73.64169095, stop_code="ABT"),
    GtfsStation("349", "Grand Central", 40.752998, -73.977056, stop_code="GCT"),
]
MNR_STATIONS = [
    GtfsStation("1", "Grand Central", 40.752998, -73.977056, stop_code="0NY"),
]


def _lirr() -> list:
    return build_mappings(
        LIRR_STATIONS,
        region_id="nyc-metro",
        feed_id="mta_lirr",
        agency_id="LI",
        feed_version="GO201_26",
        retrieved_at=FIXED_TIME,
    )


def _mnr() -> list:
    return build_mappings(
        MNR_STATIONS,
        region_id="nyc-metro",
        feed_id="mta_mnr",
        agency_id="1",
        feed_version="sha256:7abd96ef702c1100",
        retrieved_at=FIXED_TIME,
    )


def test_colliding_gtfs_stop_ids_get_distinct_canonical_ids() -> None:
    """LIRR stop 1 (Albertson) and MNR stop 1 (Grand Central) must not converge."""
    rows = _lirr() + _mnr()
    by_canonical = {r.canonical_station_id: r for r in rows}

    assert by_canonical["nyc-metro:mta_lirr:albertson"].gtfs_stop_id == "1"
    assert by_canonical["nyc-metro:mta_mnr:grand-central"].gtfs_stop_id == "1"
    assert find_duplicate_canonical_ids(rows) == []


def test_the_same_station_in_two_feeds_stays_distinct() -> None:
    """LIRR and Metro-North both serve Grand Central; each keeps its own row.

    Cross-feed equivalence is a separate, deliberate step — merging on name would
    be a guess, and a wrong merge silently corrupts routing.
    """
    ids = {r.canonical_station_id for r in _lirr() + _mnr()}

    assert "nyc-metro:mta_lirr:grand-central" in ids
    assert "nyc-metro:mta_mnr:grand-central" in ids


def test_mapping_records_the_full_provenance_key() -> None:
    """PLAN §4: (region, feed_id, agency_id, gtfs_stop_id, feed_version)."""
    row = _lirr()[0]

    assert (row.region_id, row.feed_id, row.agency_id, row.gtfs_stop_id, row.feed_version) == (
        "nyc-metro",
        "mta_lirr",
        "LI",
        "1",
        "GO201_26",
    )


def test_duplicate_names_within_a_feed_get_deterministic_suffixes() -> None:
    stations = [
        GtfsStation("b", "Main Street", 40.1, -74.1),
        GtfsStation("a", "Main Street", 40.2, -74.2),
    ]
    rows = build_mappings(
        stations,
        region_id="r",
        feed_id="f",
        agency_id="A",
        feed_version="v1",
        retrieved_at=FIXED_TIME,
    )

    # Ordered by gtfs_stop_id, so "a" takes the bare slug regardless of input order.
    assert [(r.canonical_station_id, r.gtfs_stop_id) for r in rows] == [
        ("r:f:main-street", "a"),
        ("r:f:main-street-2", "b"),
    ]


def test_rebuilding_produces_identical_output() -> None:
    """A rebuild must be a no-op diff, or every graph build churns the mapping table."""
    assert _lirr() == _lirr()


def test_feed_version_changes_do_not_change_canonical_ids() -> None:
    """The point of canonical IDs: a feed refresh renumbering stops is a mapping update."""
    renumbered = [GtfsStation("99999", "Albertson", 40.77206317, -73.64169095, stop_code="ABT")]
    after = build_mappings(
        renumbered,
        region_id="nyc-metro",
        feed_id="mta_lirr",
        agency_id="LI",
        feed_version="GO202_26",
        retrieved_at=FIXED_TIME,
    )

    assert after[0].canonical_station_id == "nyc-metro:mta_lirr:albertson"
    assert after[0].gtfs_stop_id == "99999"


def test_csv_round_trip(tmp_path: Path) -> None:
    rows = _lirr() + _mnr()
    path = write_mapping_csv(rows, tmp_path / "stations.csv")

    assert read_mapping_csv(path) == sorted(rows, key=lambda r: r.canonical_station_id)


def test_duplicate_detection_catches_a_genuine_clash() -> None:
    rows = _lirr() + _lirr()

    assert find_duplicate_canonical_ids(rows) == [
        "nyc-metro:mta_lirr:albertson",
        "nyc-metro:mta_lirr:grand-central",
    ]


def test_slugify_handles_real_station_names() -> None:
    assert slugify("Van Cortlandt Park-242 St") == "van-cortlandt-park-242-st"
    assert slugify("Harlem-148 St") == "harlem-148-st"
    assert slugify("  Spuyten Duyvil  ") == "spuyten-duyvil"
    # Accents fold to ASCII rather than disappearing.
    assert slugify("Café Station") == "cafe-station"
