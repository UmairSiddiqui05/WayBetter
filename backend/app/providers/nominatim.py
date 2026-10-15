"""GeocodingProvider backed by OpenStreetMap Nominatim (public instance), per its usage policy
(https://operations.osmfoundation.org/policies/nominatim/): at most 1 request per second,
a real identifying User-Agent, results cached on disk (no repeated identical queries), the
search bounded to the region's bounding box, and ODbL attribution shown with every result.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from app.providers.base import GeocodeResult, LatLon, ProviderError

log = structlog.get_logger(__name__)

PUBLIC_SERVER = "https://nominatim.openstreetmap.org"
TIMEOUT_SECONDS = 6.0
MIN_INTERVAL_SECONDS = 1.0
ATTRIBUTION = "Location data © OpenStreetMap contributors, ODbL 1.0 (via Nominatim)"
_TOWN_KEYS = ("town", "city", "village", "borough", "hamlet", "municipality", "suburb")


class NominatimGeocoder:
    attribution = ATTRIBUTION

    def __init__(
        self,
        cache_dir: Path,
        user_agent: str,
        bounding_box: tuple[float, float, float, float],
        base_url: str = PUBLIC_SERVER,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """`bounding_box` is (min_lat, min_lng, max_lat, max_lng)."""
        if not user_agent.strip():
            raise ValueError("Nominatim requires an identifying User-Agent")
        self._cache_dir = cache_dir
        self._base_url = base_url.rstrip("/")
        self._box = bounding_box
        self._client = client or httpx.Client(
            timeout=TIMEOUT_SECONDS, headers={"User-Agent": user_agent}
        )
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_request: float | None = None

    def search(self, query: str) -> list[GeocodeResult]:
        min_lat, min_lng, max_lat, max_lng = self._box
        params = {
            "q": query.strip(),
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 10,
            "countrycodes": "us",
            "viewbox": f"{min_lng},{max_lat},{max_lng},{min_lat}",
            "bounded": 1,
        }
        url = f"{self._base_url}/search?{urlencode(params)}"
        rows = self._fetch(url)
        results = []
        for row in rows:
            try:
                point = LatLon(float(row["lat"]), float(row["lon"]))
            except (KeyError, TypeError, ValueError):
                continue
            if not (min_lat <= point.lat <= max_lat and min_lng <= point.lon <= max_lng):
                continue
            address = row.get("address") or {}
            line = " ".join(
                part for part in (address.get("house_number"), address.get("road")) if part
            )
            name = row.get("name") or line
            town = next((address[k] for k in _TOWN_KEYS if address.get(k)), None)
            localities = tuple(dict.fromkeys(address[k] for k in _TOWN_KEYS if address.get(k)))
            results.append(
                GeocodeResult(
                    name=name,
                    town=town,
                    display_name=row.get("display_name", ""),
                    point=point,
                    kind=row.get("category") or row.get("class") or "",
                    address_line=line or None,
                    road=address.get("road"),
                    localities=localities,
                )
            )
        return results

    def _fetch(self, url: str) -> list[dict[str, Any]]:
        cache_file = self._cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:32]}.json"
        if cache_file.is_file():
            cached: list[dict[str, Any]] = json.loads(cache_file.read_text(encoding="utf-8"))
            return cached
        with self._lock:  # one request at a time, at least 1 s apart, across all threads
            if self._last_request is not None:
                wait = MIN_INTERVAL_SECONDS - (self._clock() - self._last_request)
                if wait > 0:
                    self._sleep(wait)
            self._last_request = self._clock()
            try:
                response = self._client.get(url)
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("nominatim_request_failed", error=type(exc).__name__)
                raise ProviderError(f"address lookup unavailable ({type(exc).__name__})") from exc
        if not isinstance(payload, list):
            raise ProviderError("address lookup sent an unreadable response")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload), encoding="utf-8")
        return payload
