"""DrivingProvider backed by an OSRM server (demo: the public router.project-osrm.org).

Free-flow travel times — OSRM has no live traffic, so every drive time it produces is
`estimated` (N-02). Responses are cached on disk keyed by the request URL, so a demo
that has been run once keeps working with no network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx
import structlog

from app.providers.base import DriveRoute, DriveStep, LatLon, ProviderError

log = structlog.get_logger(__name__)

PUBLIC_DEMO_SERVER = "https://router.project-osrm.org"
TIMEOUT_SECONDS = 10.0
MAX_ALTERNATIVES = 3


class OsrmDrivingProvider:
    def __init__(
        self,
        cache_dir: Path,
        base_url: str = PUBLIC_DEMO_SERVER,
        client: httpx.Client | None = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS)

    def route(self, origin: LatLon, destination: LatLon) -> DriveRoute:
        return self._routes(origin, destination, alternatives=False)[0]

    def route_options(self, origin: LatLon, destination: LatLon) -> tuple[DriveRoute, ...]:
        # The public server rejects exclude=toll ("Exclude flag combination is not supported"),
        # so avoiding tolls means pricing the alternatives it returns (D-21).
        return self._routes(origin, destination, alternatives=True)

    def _routes(
        self, origin: LatLon, destination: LatLon, alternatives: bool
    ) -> tuple[DriveRoute, ...]:
        # OSRM takes lon,lat. Rounding to ~1 m keeps cache keys stable across tiny float noise.
        coords = f"{origin.lon:.5f},{origin.lat:.5f};{destination.lon:.5f},{destination.lat:.5f}"
        query = "overview=full&geometries=polyline&steps=true"
        if alternatives:
            query += f"&alternatives={MAX_ALTERNATIVES}"
        url = f"{self._base_url}/route/v1/driving/{coords}?{query}"
        payload = self._fetch(url)
        if payload.get("code") != "Ok" or not payload.get("routes"):
            raise ProviderError(f"OSRM returned no route ({payload.get('code')})")
        return tuple(self._parse(found) for found in payload["routes"])

    @staticmethod
    def _parse(found: dict[str, Any]) -> DriveRoute:
        steps = tuple(
            DriveStep(
                name=step.get("name") or "",
                ref=step.get("ref") or "",
                exits=step.get("exits") or "",
                maneuver=step["maneuver"]["type"],
                location=LatLon(step["maneuver"]["location"][1], step["maneuver"]["location"][0]),
                distance_m=float(step["distance"]),
            )
            for step in found["legs"][0]["steps"]
        )
        return DriveRoute(
            duration_s=float(found["duration"]),
            distance_m=float(found["distance"]),
            polyline=found["geometry"],
            steps=steps,
        )

    def _fetch(self, url: str) -> dict[str, Any]:
        cache_file = self._cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:32]}.json"
        if cache_file.is_file():
            cached: dict[str, Any] = json.loads(cache_file.read_text(encoding="utf-8"))
            return cached
        try:
            response = self._client.get(url)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("osrm_request_failed", error=type(exc).__name__)
            raise ProviderError(f"driving provider unavailable: {type(exc).__name__}") from exc
        if payload.get("code") == "Ok":
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(payload), encoding="utf-8")
        return payload
