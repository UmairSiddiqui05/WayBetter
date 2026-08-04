"""GTFS validation and station extraction.

Fixtures mirror shapes observed in the real launch feeds: subway-style feeds with
`location_type=1` parent stations, and flat commuter-rail feeds (LIRR,
Metro-North) with neither `calendar.txt` nor `feed_info.txt`.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.ingestion import FeedArchive, GtfsArchiveError, extract_stations, validate_feed

AGENCY = "agency_id,agency_name,agency_timezone\nTEST,Test Agency,America/New_York\n"
ROUTES = "route_id,agency_id,route_short_name,route_type\nR1,TEST,1,2\n"
TRIPS = "route_id,service_id,trip_id\nR1,S1,T1\n"
STOP_TIMES = "trip_id,arrival_time,departure_time,stop_id,stop_sequence\nT1,08:00:00,08:00:00,S,1\n"
CALENDAR_DATES = "service_id,date,exception_type\nS1,20260706,1\n"
CALENDAR = (
    "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
    "S1,1,1,1,1,1,0,0,20260101,20261231\n"
)

FLAT_STOPS = (
    "stop_id,stop_code,stop_name,stop_lat,stop_lon,stop_url\n"
    "1,ABT,Albertson,40.77206317,-73.64169095,https://example.test/albertson\n"
    "2,GCT,Grand Central,40.752998,-73.977056,\n"
)

PARENT_STATION_STOPS = (
    "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station\n"
    "101,Van Cortlandt Park-242 St,40.889248,-73.898583,1,\n"
    "101N,Van Cortlandt Park-242 St,40.889248,-73.898583,0,101\n"
    "101S,Van Cortlandt Park-242 St,40.889248,-73.898583,0,101\n"
    "103,238 St,40.884667,-73.900870,1,\n"
)


def make_feed(path: Path, tables: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in tables.items():
            archive.writestr(name, content)
    return path


def base_tables(stops: str = FLAT_STOPS) -> dict[str, str]:
    return {
        "agency.txt": AGENCY,
        "stops.txt": stops,
        "routes.txt": ROUTES,
        "trips.txt": TRIPS,
        "stop_times.txt": STOP_TIMES,
        "calendar.txt": CALENDAR,
    }


# --- Validation --------------------------------------------------------------


def test_a_complete_feed_validates_cleanly(tmp_path: Path) -> None:
    tables = base_tables() | {"feed_info.txt": "feed_version\nv1\n"}
    with FeedArchive(make_feed(tmp_path / "f.zip", tables)) as archive:
        report = validate_feed(archive, "test")

    assert report.ok
    assert report.warnings == []


def test_missing_required_tables_are_errors(tmp_path: Path) -> None:
    tables = base_tables()
    del tables["stop_times.txt"]
    del tables["routes.txt"]

    with FeedArchive(make_feed(tmp_path / "f.zip", tables)) as archive:
        report = validate_feed(archive, "test")

    assert not report.ok
    assert "routes.txt" in report.errors[0]
    assert "stop_times.txt" in report.errors[0]


def test_calendar_dates_only_is_a_warning_not_an_error(tmp_path: Path) -> None:
    """LIRR and Metro-North ship no calendar.txt; rejecting them would drop two launch feeds."""
    tables = base_tables()
    del tables["calendar.txt"]
    tables["calendar_dates.txt"] = CALENDAR_DATES

    with FeedArchive(make_feed(tmp_path / "f.zip", tables)) as archive:
        report = validate_feed(archive, "test")

    assert report.ok
    assert any("no calendar.txt" in w for w in report.warnings)


def test_no_calendar_at_all_is_an_error(tmp_path: Path) -> None:
    tables = base_tables()
    del tables["calendar.txt"]

    with FeedArchive(make_feed(tmp_path / "f.zip", tables)) as archive:
        report = validate_feed(archive, "test")

    assert not report.ok
    assert any("neither calendar.txt nor calendar_dates.txt" in e for e in report.errors)


def test_unusable_coordinates_are_errors(tmp_path: Path) -> None:
    stops = "stop_id,stop_name,stop_lat,stop_lon\n1,Good,40.7,-73.9\n2,Blank,,\n3,Null Island,0,0\n"
    with FeedArchive(make_feed(tmp_path / "f.zip", base_tables(stops))) as archive:
        report = validate_feed(archive, "test")

    assert not report.ok
    assert "2 stop(s) have unusable coordinates" in report.errors[0]


def test_duplicate_stop_ids_are_errors(tmp_path: Path) -> None:
    stops = "stop_id,stop_name,stop_lat,stop_lon\n1,A,40.7,-73.9\n1,B,40.8,-73.8\n"
    with FeedArchive(make_feed(tmp_path / "f.zip", base_tables(stops))) as archive:
        report = validate_feed(archive, "test")

    assert not report.ok
    assert any("duplicate stop_id" in e for e in report.errors)


def test_a_feed_with_no_trips_is_an_error(tmp_path: Path) -> None:
    tables = base_tables() | {"trips.txt": "route_id,service_id,trip_id\n"}
    with FeedArchive(make_feed(tmp_path / "f.zip", tables)) as archive:
        report = validate_feed(archive, "test")

    assert not report.ok
    assert any("carries no service" in e for e in report.errors)


def test_a_non_zip_file_is_rejected(tmp_path: Path) -> None:
    junk = tmp_path / "not.zip"
    junk.write_text("this is not a zip", encoding="utf-8")

    with pytest.raises(GtfsArchiveError, match="not a readable GTFS archive"):
        FeedArchive(junk)


# --- Versioning --------------------------------------------------------------


def test_feed_version_comes_from_feed_info_when_published(tmp_path: Path) -> None:
    tables = base_tables() | {"feed_info.txt": "feed_version\nGO201_26\n"}
    with FeedArchive(make_feed(tmp_path / "f.zip", tables)) as archive:
        assert archive.feed_version() == "GO201_26"


def test_feed_version_falls_back_to_a_content_hash(tmp_path: Path) -> None:
    """Metro-North publishes no feed_info.txt, so it declares no version."""
    with FeedArchive(make_feed(tmp_path / "f.zip", base_tables())) as archive:
        version = archive.feed_version()
        report = validate_feed(archive, "test")

    assert version.startswith("sha256:")
    assert any("no feed_info.txt" in w for w in report.warnings)


def test_content_hash_changes_only_when_content_changes(tmp_path: Path) -> None:
    same_a = make_feed(tmp_path / "a.zip", base_tables())
    same_b = make_feed(tmp_path / "b.zip", base_tables())
    different = make_feed(tmp_path / "c.zip", base_tables(FLAT_STOPS + "3,X,New,40.1,-73.1,\n"))

    with FeedArchive(same_a) as a, FeedArchive(same_b) as b, FeedArchive(different) as c:
        assert a.feed_version() == b.feed_version()
        assert a.feed_version() != c.feed_version()


def test_agency_ids_are_read_from_the_feed(tmp_path: Path) -> None:
    with FeedArchive(make_feed(tmp_path / "f.zip", base_tables())) as archive:
        assert archive.agency_ids() == ("TEST",)


# --- Station extraction ------------------------------------------------------


def test_flat_feeds_yield_every_standalone_stop(tmp_path: Path) -> None:
    with FeedArchive(make_feed(tmp_path / "f.zip", base_tables())) as archive:
        stations = extract_stations(archive)

    assert [s.name for s in stations] == ["Albertson", "Grand Central"]
    assert stations[0].stop_code == "ABT"
    assert stations[1].stop_url is None


def test_parent_station_feeds_yield_stations_not_platforms(tmp_path: Path) -> None:
    """Subway hangs platforms off `location_type=1` parents; you drive to the parent."""
    tables = base_tables(PARENT_STATION_STOPS)
    with FeedArchive(make_feed(tmp_path / "f.zip", tables)) as archive:
        stations = extract_stations(archive)

    assert [s.gtfs_stop_id for s in stations] == ["103", "101"]
    assert all("N" not in s.gtfs_stop_id and "S" not in s.gtfs_stop_id for s in stations)


def test_stops_with_unusable_coordinates_are_dropped(tmp_path: Path) -> None:
    stops = "stop_id,stop_name,stop_lat,stop_lon\n1,Good,40.7,-73.9\n2,Null Island,0,0\n"
    with FeedArchive(make_feed(tmp_path / "f.zip", base_tables(stops))) as archive:
        stations = extract_stations(archive)

    assert [s.name for s in stations] == ["Good"]


def test_extraction_is_deterministic(tmp_path: Path) -> None:
    with FeedArchive(make_feed(tmp_path / "f.zip", base_tables())) as archive:
        first = extract_stations(archive)
        second = extract_stations(archive)

    assert first == second
