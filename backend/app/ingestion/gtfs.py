"""GTFS archive reading, structural validation, and station extraction.

Deliberately not a full GTFS validator — Google's and MobilityData's already
exist. This checks the things that would make an ingest silently wrong: missing
required tables, an unusable calendar, stops without coordinates, and the
agency/version metadata the canonical station mapping keys on (N-03, N-08).

Real-feed quirks this had to accommodate (all observed, not anticipated):

- LIRR and Metro-North ship **no `calendar.txt`** — service runs entirely off
  `calendar_dates.txt`. GTFS permits this, so requiring `calendar.txt` would
  reject two launch feeds.
- Metro-North ships **no `feed_info.txt`**, so it publishes no `feed_version`.
  Version falls back to a content hash, which still changes exactly when the
  data changes.
- Subway marks stations with `location_type=1` and hangs platforms off them via
  `parent_station`; LIRR and Metro-North have flat stop lists with neither
  column populated. Station extraction handles both shapes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_TABLES = ("agency.txt", "stops.txt", "routes.txt", "trips.txt", "stop_times.txt")
CALENDAR_TABLES = ("calendar.txt", "calendar_dates.txt")

_LOCATION_TYPE_STATION = "1"
_LOCATION_TYPE_STOP = ("", "0")


@dataclass(frozen=True, slots=True)
class GtfsStation:
    """A station as the feed describes it, before canonical identity is assigned."""

    gtfs_stop_id: str
    name: str
    lat: float
    lng: float
    stop_code: str | None = None
    stop_url: str | None = None


@dataclass(slots=True)
class ValidationReport:
    """Errors block ingestion; warnings are recorded and surfaced to the human."""

    feed_id: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class GtfsArchiveError(RuntimeError):
    """The file is not a readable GTFS zip at all."""


class FeedArchive:
    """Read-only view over a GTFS zip. Streams tables; never extracts to disk."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        try:
            self._zip = zipfile.ZipFile(self.path)
        except (zipfile.BadZipFile, FileNotFoundError) as exc:
            raise GtfsArchiveError(f"not a readable GTFS archive: {self.path}") from exc

    def __enter__(self) -> FeedArchive:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._zip.close()

    @property
    def tables(self) -> frozenset[str]:
        # Some publishers nest the feed one directory deep.
        return frozenset(Path(name).name for name in self._zip.namelist())

    def has(self, table: str) -> bool:
        return table in self.tables

    def _member(self, table: str) -> str:
        for name in self._zip.namelist():
            if Path(name).name == table:
                return name
        raise KeyError(table)

    def read_table(self, table: str) -> list[dict[str, str]]:
        """Rows of a GTFS table. `utf-8-sig` because agency exports carry BOMs."""
        with self._zip.open(self._member(table)) as raw:
            return list(csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig")))

    def content_hash(self) -> str:
        """SHA-256 of the archive bytes — the fallback feed version."""
        digest = hashlib.sha256()
        with self.path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def agency_ids(self) -> tuple[str, ...]:
        rows = self.read_table("agency.txt")
        # agency_id is optional in single-agency feeds; fall back to the name.
        return tuple(
            dict.fromkeys(row.get("agency_id") or row.get("agency_name", "") for row in rows)
        )

    def feed_version(self) -> str:
        """Publisher-declared version, or a content hash when none is published."""
        if self.has("feed_info.txt"):
            rows = self.read_table("feed_info.txt")
            if rows and rows[0].get("feed_version"):
                return rows[0]["feed_version"]
        return f"sha256:{self.content_hash()[:16]}"


def validate_feed(archive: FeedArchive, feed_id: str) -> ValidationReport:
    """Structural checks that catch a silently unusable feed."""
    report = ValidationReport(feed_id=feed_id)

    missing = [table for table in REQUIRED_TABLES if not archive.has(table)]
    if missing:
        report.errors.append(f"missing required tables: {', '.join(missing)}")
        return report  # Everything below reads those tables.

    if not any(archive.has(table) for table in CALENDAR_TABLES):
        report.errors.append("feed has neither calendar.txt nor calendar_dates.txt")
    elif not archive.has("calendar.txt"):
        report.warnings.append(
            "no calendar.txt — service comes entirely from calendar_dates.txt "
            "(normal for LIRR/Metro-North; holiday and weekend fixtures depend on it)"
        )

    if not archive.has("feed_info.txt"):
        report.warnings.append(
            "no feed_info.txt — feed publishes no feed_version; falling back to a content hash"
        )

    if not archive.agency_ids():
        report.errors.append("agency.txt is empty")

    stops = archive.read_table("stops.txt")
    if not stops:
        report.errors.append("stops.txt is empty")
        return report

    bad_coords = [
        row.get("stop_id", "?")
        for row in stops
        if not _parse_coord(row.get("stop_lat")) or not _parse_coord(row.get("stop_lon"))
    ]
    if bad_coords:
        report.errors.append(
            f"{len(bad_coords)} stop(s) have unusable coordinates "
            f"(first few: {', '.join(bad_coords[:5])})"
        )

    counts = Counter(row.get("stop_id", "") for row in stops)
    duplicates = sorted(sid for sid, count in counts.items() if count > 1)
    if duplicates:
        report.errors.append(f"duplicate stop_id values: {', '.join(duplicates[:5])}")

    if not archive.read_table("trips.txt"):
        report.errors.append("trips.txt is empty — feed carries no service")

    return report


def extract_stations(archive: FeedArchive) -> list[GtfsStation]:
    """Stations, not platforms.

    Feeds that use `location_type=1` (subway) yield their parent stations; flat
    feeds (LIRR, Metro-North) yield every standalone stop. Platforms are dropped
    either way — a park-and-ride candidate is a place you drive to, not a track.
    """
    rows = archive.read_table("stops.txt")
    has_parent_stations = any(row.get("location_type") == _LOCATION_TYPE_STATION for row in rows)

    stations: list[GtfsStation] = []
    for row in rows:
        location_type = (row.get("location_type") or "").strip()
        if has_parent_stations:
            if location_type != _LOCATION_TYPE_STATION:
                continue
        else:
            has_parent = bool((row.get("parent_station") or "").strip())
            if location_type not in _LOCATION_TYPE_STOP or has_parent:
                continue

        lat = _parse_coord(row.get("stop_lat"))
        lng = _parse_coord(row.get("stop_lon"))
        name = (row.get("stop_name") or "").strip()
        stop_id = (row.get("stop_id") or "").strip()
        if lat is None or lng is None or not name or not stop_id:
            continue

        stations.append(
            GtfsStation(
                gtfs_stop_id=stop_id,
                name=name,
                lat=lat,
                lng=lng,
                stop_code=(row.get("stop_code") or "").strip() or None,
                stop_url=(row.get("stop_url") or "").strip() or None,
            )
        )

    stations.sort(key=lambda s: (s.name, s.gtfs_stop_id))
    return stations


def _parse_coord(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    # 0,0 is the classic "coordinate missing" placeholder, not the Gulf of Guinea.
    return None if parsed == 0.0 else parsed
