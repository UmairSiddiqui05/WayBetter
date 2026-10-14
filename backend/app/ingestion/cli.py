"""Ingestion CLI: `waybetter-ingest <command>` (or `python -m app.ingestion.cli`).

    check-region       validate the region config and report what data is missing
    fetch              download + validate enabled feeds, write provenance metadata
    build-station-map  assign canonical station IDs from downloaded archives

Nothing here writes to the database; the output is files under `data/`, reviewed
by a human and versioned with the graph bundle (N-08).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from app.ingestion.feeds import (
    FeedDownloadError,
    archive_path,
    build_metadata,
    download_feed,
    metadata_path,
)
from app.ingestion.gtfs import FeedArchive, GtfsArchiveError, extract_stations, validate_feed
from app.regions.loader import REPO_ROOT, load_region_config, resolve_region_path
from app.regions.schema import RegionConfig

DEFAULT_REGION = "data/regions/nyc-metro.yaml"
DEFAULT_GTFS_DIR = "data/gtfs"


def _station_map_path(region: RegionConfig) -> Path:
    return REPO_ROOT / "data" / "regions" / f"{region.region_id}-stations.csv"


def cmd_check_region(args: argparse.Namespace) -> int:
    region = load_region_config(args.region)
    print(f"region      : {region.region_id} ({region.name})")
    print(f"timezone    : {region.timezone}")
    box = region.bounding_box
    print(f"bounding box: {box.min_lat},{box.min_lng} .. {box.max_lat},{box.max_lng}")
    print(f"parking buf : {region.default_parking_buffer_minutes} min")

    print(f"\nfeeds ({len(region.feeds)}):")
    for feed in region.feeds:
        if not feed.enabled:
            state = "disabled"
        elif feed.blocked_reason:
            state = "blocked"
        else:
            state = "enabled"
        licence = "verified" if feed.license.verified else "UNVERIFIED LICENCE"
        print(f"  {feed.feed_id:<12} {state:<9} {licence:<18} {feed.agency_name}")
        if feed.blocked_reason:
            print(f"               reason: {' '.join(feed.blocked_reason.split())}")

    problems: list[str] = []

    unverified = [f.feed_id for f in region.enabled_feeds() if not f.license.verified]
    if unverified:
        problems.append(
            f"{len(unverified)} enabled feed(s) have an unverified licence "
            f"({', '.join(unverified)}) — a human must confirm the terms (N-09)"
        )

    print("\nreferenced paths:")
    referenced: list[tuple[str, Path]] = [
        (f"zone:{zone.zone_id}", resolve_region_path(zone.geojson_path))
        for zone in region.city_driving_zones
    ]
    referenced += [
        ("fares_dir", resolve_region_path(region.data_files.fares_dir)),
        ("tolls_dir", resolve_region_path(region.data_files.tolls_dir)),
        ("parking_dir", resolve_region_path(region.data_files.parking_dir)),
        ("graph_bundle", resolve_region_path(region.graph_bundle.path)),
    ]
    for label, path in referenced:
        exists = path.exists()
        print(f"  {'ok     ' if exists else 'MISSING'} {label:<22} {path.relative_to(REPO_ROOT)}")
        if not exists:
            problems.append(f"{label} does not exist: {path.relative_to(REPO_ROOT)}")

    if problems:
        print(f"\n{len(problems)} outstanding item(s):")
        for problem in problems:
            print(f"  - {problem}")
    else:
        print("\nNo outstanding items.")

    # Config validity is the exit status; missing data is reported, not fatal —
    # this command is meant to be run against an incomplete region.
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    # Credentialed feeds read their portal login from .env (never from the region
    # config). Real environment variables win over the file.
    load_dotenv(REPO_ROOT / ".env", override=False)
    region = load_region_config(args.region)
    gtfs_dir = resolve_region_path(args.gtfs_dir)
    targets = region.fetchable_feeds()

    skipped = [f for f in region.feeds if f not in targets]
    for feed in skipped:
        if feed.blocked_reason or not feed.enabled:
            reason = feed.blocked_reason or "disabled"
        else:
            reason = f"set {', '.join(feed.credential_env)} in .env to fetch"
        print(f"skip  {feed.feed_id:<12} {' '.join(reason.split())[:90]}")

    if not targets:
        print("\nNo fetchable feeds in this region.")
        return 1

    failures = 0
    for feed in targets:
        try:
            result = download_feed(feed, gtfs_dir, force=args.force)
        except FeedDownloadError as exc:
            print(f"FAIL  {feed.feed_id:<12} {exc}")
            failures += 1
            continue

        try:
            with FeedArchive(result.path) as archive:
                report = validate_feed(archive, feed.feed_id)
                version = archive.feed_version()
                agency_ids = list(archive.agency_ids())
                station_count = len(extract_stations(archive))
        except GtfsArchiveError as exc:
            print(f"FAIL  {feed.feed_id:<12} {exc}")
            failures += 1
            continue

        build_metadata(
            feed,
            result,
            feed_version=version,
            agency_ids=agency_ids,
            errors=report.errors,
            warnings=report.warnings,
            retrieved_at=datetime.now(UTC),
        ).write(metadata_path(feed, gtfs_dir))

        status = "ok  " if report.ok else "BAD "
        change = "updated" if result.changed else "unchanged"
        print(
            f"{status}  {feed.feed_id:<12} {result.size_bytes / 1_048_576:5.1f} MB  {change:<9} "
            f"version={version}  agencies={','.join(agency_ids)}  stations={station_count}"
        )
        for error in report.errors:
            print(f"        ERROR   {error}")
            failures += 1
        for warning in report.warnings:
            print(f"        warning {' '.join(warning.split())}")

        if not feed.license.verified:
            print("        warning licence not yet verified by a human (N-09)")

    return 1 if failures else 0


def cmd_build_station_map(args: argparse.Namespace) -> int:
    # Imported here so `check-region` stays usable if this module grows heavier deps.
    from app.ingestion.stations import (
        build_mappings,
        find_duplicate_canonical_ids,
        write_mapping_csv,
    )

    region = load_region_config(args.region)
    gtfs_dir = resolve_region_path(args.gtfs_dir)
    rows = []
    missing = []

    for feed in region.enabled_feeds():
        path = archive_path(feed, gtfs_dir)
        if not path.exists():
            missing.append(feed.feed_id)
            continue
        with FeedArchive(path) as archive:
            stations = extract_stations(archive)
            agency_ids = archive.agency_ids() or ("",)
            feed_rows = build_mappings(
                stations,
                region_id=region.region_id,
                feed_id=feed.feed_id,
                # A GTFS feed may declare several agencies; the first is the
                # publisher. Multi-agency splitting is a per-agency rule-module
                # concern (N-03), not something to guess at here.
                agency_id=agency_ids[0],
                feed_version=archive.feed_version(),
            )
        rows.extend(feed_rows)
        print(f"  {feed.feed_id:<12} {len(feed_rows):>4} stations")

    for feed_id in missing:
        print(f"  {feed_id:<12}    - archive not downloaded, skipped")

    if not rows:
        print("\nNo station data. Run `fetch` first.")
        return 1

    duplicates = find_duplicate_canonical_ids(rows)
    if duplicates:
        print(f"\nERROR: duplicate canonical IDs: {', '.join(duplicates[:10])}")
        return 1

    out = Path(args.out) if args.out else _station_map_path(region)
    write_mapping_csv(rows, out)
    print(f"\n{len(rows)} stations -> {out.relative_to(REPO_ROOT)}")
    return 0


def cmd_osm_plan(args: argparse.Namespace) -> int:
    """Print the OSM extract pipeline for this region, with the bbox from config.

    Prints rather than runs: the download hosts were unreachable from the build
    environment, so the commands are unverified. Deriving them from the region
    config is what keeps the extract and the request-validation boundary from
    drifting apart — the graph must cover at least what the API accepts (N-03).
    """
    region = load_region_config(args.region)
    box = region.bounding_box
    # Padding so routing near the edge of the region does not fall off the graph:
    # a drive leg may legitimately leave the box and come back.
    pad = args.pad_degrees
    left, bottom = box.min_lng - pad, box.min_lat - pad
    right, top = box.max_lng + pad, box.max_lat + pad
    osm_dir = Path("data/osm")

    print(f"# OSM extract plan for {region.region_id}")
    print(f"# Region box {box.min_lat},{box.min_lng} .. {box.max_lat},{box.max_lng}")
    print(f"# Clip box (padded {pad}°): {bottom},{left} .. {top},{right}")
    print("#")
    print("# UNVERIFIED: generated from config, never executed here — the build")
    print("# environment's egress policy denied download.geofabrik.de. Check the")
    print("# current Geofabrik paths before trusting these URLs.")
    print("#")
    print("# Requires: osmium-tool (apt install osmium-tool)")
    print()
    sources = {
        "new-york": "https://download.geofabrik.de/north-america/us/new-york-latest.osm.pbf",
        "new-jersey": "https://download.geofabrik.de/north-america/us/new-jersey-latest.osm.pbf",
        "connecticut": "https://download.geofabrik.de/north-america/us/connecticut-latest.osm.pbf",
        "pennsylvania": "https://download.geofabrik.de/north-america/us/pennsylvania-latest.osm.pbf",
        "massachusetts": "https://download.geofabrik.de/north-america/us/massachusetts-latest.osm.pbf",
    }
    for name, url in sources.items():
        print(f"curl -fL --retry 3 -o {osm_dir}/{name}.osm.pbf \\\n  {url}")
        print(f"curl -fL -o {osm_dir}/{name}.osm.pbf.md5 {url}.md5")
    print()
    merged = f"{osm_dir}/merged.osm.pbf"
    inputs = " ".join(f"{osm_dir}/{name}.osm.pbf" for name in sources)
    print(f"osmium merge {inputs} -o {merged}")
    print(
        f"osmium extract --bbox {left},{bottom},{right},{top} "
        f"--strategy complete_ways {merged} -o {osm_dir}/{region.region_id}.osm.pbf"
    )
    print()
    print("# Record provenance alongside the extract (N-09): OSM is ODbL —")
    print("# '© OpenStreetMap contributors' must appear in the client UI.")
    print(f"# Write {osm_dir}/{region.region_id}.source.json with the source URLs,")
    print("# the md5s, the licence, and the retrieval date.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="waybetter-ingest", description=__doc__)
    parser.add_argument("--region", default=DEFAULT_REGION, help="path to the region config")
    parser.add_argument("--gtfs-dir", default=DEFAULT_GTFS_DIR, help="where feed archives live")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check-region", help="validate the region config and report missing data")

    fetch = sub.add_parser("fetch", help="download and validate enabled feeds")
    fetch.add_argument(
        "--force", action="store_true", help="rewrite the archive even if bytes are unchanged"
    )

    station_map = sub.add_parser("build-station-map", help="assign canonical station IDs")
    station_map.add_argument(
        "--out", help="output CSV (defaults to data/regions/<region>-stations.csv)"
    )

    osm = sub.add_parser("osm-plan", help="print the OSM extract pipeline for this region")
    osm.add_argument(
        "--pad-degrees",
        type=float,
        default=0.25,
        help="padding around the region box so edge routing stays on the graph",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "check-region": cmd_check_region,
        "fetch": cmd_fetch,
        "build-station-map": cmd_build_station_map,
        "osm-plan": cmd_osm_plan,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
