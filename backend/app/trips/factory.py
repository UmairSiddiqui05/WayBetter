"""Builds the trip service from region data. The only place adapters are chosen (N-04)."""

from __future__ import annotations

import csv
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.pricing import load_pricing_data
from app.providers.base import LatLon
from app.providers.gtfs_transit import GtfsTransitProvider
from app.providers.osrm import OsrmDrivingProvider
from app.regions import get_region_config
from app.regions.loader import REPO_ROOT, resolve_region_path
from app.trips.corridor import load_corridor
from app.trips.service import Station, TripSearchService

OSRM_CACHE_DIR = REPO_ROOT / "data" / "cache" / "osrm"


@lru_cache(maxsize=1)
def get_trip_service() -> TripSearchService:
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
