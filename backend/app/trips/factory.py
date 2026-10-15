"""Builds the trip service from region data. The only place adapters are chosen (N-04)."""

from __future__ import annotations

import csv
import threading
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import structlog

from app.pricing import load_pricing_data
from app.providers.base import LatLon
from app.providers.gtfs_transit import GtfsTransitProvider
from app.providers.osrm import OsrmDrivingProvider
from app.regions import get_region_config
from app.regions.loader import REPO_ROOT, resolve_region_path
from app.trips.corridor import load_corridor
from app.trips.models import LatLng, TripSearchRequest
from app.trips.service import Station, TripSearchService

OSRM_CACHE_DIR = REPO_ROOT / "data" / "cache" / "osrm"

log = structlog.get_logger(__name__)
_build_lock = threading.Lock()


def get_trip_service() -> TripSearchService:
    """The process-wide trip service. The first call loads the GTFS archive (~10 s); the
    lock makes a request that arrives mid-preload wait for it instead of loading a second copy."""
    with _build_lock:
        return _build_trip_service()


def transit_archive_path() -> Path:
    region = get_region_config()
    corridor = load_corridor(
        resolve_region_path(f"data/regions/{region.region_id}-demo-corridor.yaml")
    )
    return resolve_region_path(f"data/gtfs/{corridor.transit_feed}.zip")


def preload_in_background() -> threading.Thread | None:
    """Build the trip service on a daemon thread so the first search is fast while /healthz
    answers immediately. Skipped (None) when the GTFS archive is missing."""
    archive = transit_archive_path()
    if not archive.is_file():
        log.warning("trip_service_preload_skipped", reason="no gtfs archive", path=str(archive))
        return None

    def _run() -> None:
        try:
            _warm_up(get_trip_service())
            log.info("trip_service_preloaded")
        except Exception as exc:  # the first request retries and reports the real error
            log.warning("trip_service_preload_failed", error=repr(exc))

    thread = threading.Thread(target=_run, name="trip-service-preload", daemon=True)
    thread.start()
    return thread


def _warm_up(service: TripSearchService) -> None:
    """One preset search (first origin -> first destination, next weekday 07:00) so the rail
    shapes it reads are cached before a real user asks. Uses cached driving routes only if
    warmed; a network failure here just logs and the first real search pays the cost."""
    corridor = service.corridor
    if not corridor.origins or not corridor.destinations:
        return
    depart = datetime.now(service.timezone).replace(hour=7, minute=0, second=0, microsecond=0)
    depart += timedelta(days=1)
    while depart.weekday() >= 5:
        depart += timedelta(days=1)
    origin, dest = corridor.origins[0], corridor.destinations[0]
    service.search(
        TripSearchRequest(
            origin=LatLng(lat=origin.lat, lng=origin.lng),
            destination=LatLng(lat=dest.lat, lng=dest.lng),
            time_mode="leave_at",
            target_time=depart,
        ),
        now=depart,
    )


@lru_cache(maxsize=1)
def _build_trip_service() -> TripSearchService:
    region = get_region_config()
    corridor = load_corridor(
        resolve_region_path(f"data/regions/{region.region_id}-demo-corridor.yaml")
    )
    with resolve_region_path(f"data/regions/{region.region_id}-stations.csv").open(
        encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    stations = {
        r["canonical_station_id"]: Station(
            station_id=r["canonical_station_id"],
            name=r["stop_name"],
            point=LatLon(float(r["stop_lat"]), float(r["stop_lon"])),
        )
        for r in rows
    }
    feed_rows = [r for r in rows if r["feed_id"] == corridor.transit_feed]
    transit = GtfsTransitProvider(
        archive=resolve_region_path(f"data/gtfs/{corridor.transit_feed}.zip"),
        station_to_stop={r["canonical_station_id"]: r["gtfs_stop_id"] for r in feed_rows},
        stop_coords={
            r["gtfs_stop_id"]: LatLon(float(r["stop_lat"]), float(r["stop_lon"])) for r in feed_rows
        },
        timezone=ZoneInfo(region.timezone),
    )
    return TripSearchService(
        region=region,
        corridor=corridor,
        pricing=load_pricing_data(region),
        stations=stations,
        driving=OsrmDrivingProvider(cache_dir=OSRM_CACHE_DIR),
        transit=transit,
    )
