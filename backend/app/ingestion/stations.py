"""Canonical station identity (N-03).

Why this exists, concretely: in the launch feeds, LIRR `stop_id=1` is Albertson
and Metro-North `stop_id=1` is Grand Central. Raw GTFS stop IDs are unique only
*within* a feed, and they are not stable across feed versions. Anything that
outlives a single feed download — parking rows, precomputed transit times, saved
places, API responses — must key on a canonical ID instead.

The mapping table records `(region, feed_id, agency_id, gtfs_stop_id,
feed_version)` for every canonical ID, exactly as PLAN §4 requires, so a feed
refresh that renumbers stops is a mapping update rather than silent corruption.

Canonical IDs are `<region>:<feed>:<name-slug>` — readable in a log and stable
while the station's name is, which outlasts its stop_id. Same-name collisions
inside one feed get a deterministic numeric suffix ordered by `gtfs_stop_id`, so
rebuilding the table twice produces byte-identical output.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.ingestion.gtfs import GtfsStation

MAPPING_COLUMNS = (
    "canonical_station_id",
    "region_id",
    "feed_id",
    "agency_id",
    "gtfs_stop_id",
    "feed_version",
    "stop_name",
    "stop_lat",
    "stop_lon",
    "stop_code",
    "stop_url",
    "retrieved_at",
)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class StationMapping:
    """One row of the canonical station mapping table."""

    canonical_station_id: str
    region_id: str
    feed_id: str
    agency_id: str
    gtfs_stop_id: str
    feed_version: str
    stop_name: str
    stop_lat: float
    stop_lon: float
    stop_code: str | None
    stop_url: str | None
    retrieved_at: str


def slugify(name: str) -> str:
    """ASCII, lowercase, hyphen-joined. Accents fold rather than vanish."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    return _SLUG_STRIP.sub("-", ascii_only.lower()).strip("-")


def build_mappings(
    stations: list[GtfsStation],
    *,
    region_id: str,
    feed_id: str,
    agency_id: str,
    feed_version: str,
    retrieved_at: datetime | None = None,
) -> list[StationMapping]:
    """Assign canonical IDs to one feed's stations. Deterministic for a given input."""
    timestamp = (retrieved_at or datetime.now(UTC)).isoformat()

    by_slug: dict[str, list[GtfsStation]] = defaultdict(list)
    for station in stations:
        by_slug[slugify(station.name) or "station"].append(station)

    rows: list[StationMapping] = []
    for slug, group in by_slug.items():
        ordered = sorted(group, key=lambda s: s.gtfs_stop_id)
        for index, station in enumerate(ordered, start=1):
            # A bare slug for the first, "-2", "-3" … for genuine duplicates. Two
            # stations sharing a name in one feed is a data-quality smell worth
            # seeing in the ID rather than papering over.
            suffix = "" if index == 1 else f"-{index}"
            rows.append(
                StationMapping(
                    canonical_station_id=f"{region_id}:{feed_id}:{slug}{suffix}",
                    region_id=region_id,
                    feed_id=feed_id,
                    agency_id=agency_id,
                    gtfs_stop_id=station.gtfs_stop_id,
                    feed_version=feed_version,
                    stop_name=station.name,
                    stop_lat=station.lat,
                    stop_lon=station.lng,
                    stop_code=station.stop_code,
                    stop_url=station.stop_url,
                    retrieved_at=timestamp,
                )
            )

    rows.sort(key=lambda r: r.canonical_station_id)
    return rows


def find_duplicate_canonical_ids(rows: list[StationMapping]) -> list[str]:
    """Canonical IDs must be unique across the whole table, not just per feed."""
    seen: dict[str, int] = defaultdict(int)
    for row in rows:
        seen[row.canonical_station_id] += 1
    return sorted(cid for cid, count in seen.items() if count > 1)


def write_mapping_csv(rows: list[StationMapping], path: str | Path) -> Path:
    """Write the table. CSV because a human reviews this file by eye."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MAPPING_COLUMNS))
        writer.writeheader()
        for row in sorted(rows, key=lambda r: r.canonical_station_id):
            writer.writerow({k: ("" if v is None else v) for k, v in asdict(row).items()})
    return target


def read_mapping_csv(path: str | Path) -> list[StationMapping]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        return [
            StationMapping(
                canonical_station_id=row["canonical_station_id"],
                region_id=row["region_id"],
                feed_id=row["feed_id"],
                agency_id=row["agency_id"],
                gtfs_stop_id=row["gtfs_stop_id"],
                feed_version=row["feed_version"],
                stop_name=row["stop_name"],
                stop_lat=float(row["stop_lat"]),
                stop_lon=float(row["stop_lon"]),
                stop_code=row["stop_code"] or None,
                stop_url=row["stop_url"] or None,
                retrieved_at=row["retrieved_at"],
            )
            for row in csv.DictReader(handle)
        ]
