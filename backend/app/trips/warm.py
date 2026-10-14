"""Warm the driving-route cache for every preset origin x destination (demo step 6).

Run once with network (`make warm-cache`); afterwards every preset search is served from
`data/cache/osrm/` and the GTFS file on disk, so the demo works with Wi-Fi off. Routes do
not depend on time of day (OSRM is free-flow), so one pass covers every departure time.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

from app.trips.factory import OSRM_CACHE_DIR, get_trip_service
from app.trips.models import TripSearchRequest


def main() -> int:
    service = get_trip_service()
    corridor = service.corridor
    depart = datetime.now(service.timezone).replace(hour=7, minute=0, second=0, microsecond=0)
    depart += timedelta(days=1)
    while depart.weekday() >= 5:
        depart += timedelta(days=1)
    failures = 0
    for origin in corridor.origins:
        for dest in corridor.destinations:
            request = TripSearchRequest.model_validate(
                {
                    "origin": {"lat": origin.lat, "lng": origin.lng},
                    "destination": {"lat": dest.lat, "lng": dest.lng},
                    "time_mode": "leave_at",
                    "target_time": depart.isoformat(),
                }
            )
            response = service.search(request, now=depart)
            best = response.routes[0] if response.routes else None
            line = f"{origin.label:<34} -> {dest.label:<34} {len(response.routes)} options"
            if best:
                line += f"; best: {best.summary} ${best.cost_breakdown.total:.2f}"
            print(line)
            if len(response.routes) < service.option_count:
                failures += 1
                for note in response.disclaimers:
                    print(f"    ! {note}")
    files = len(list(OSRM_CACHE_DIR.glob("*.json")))
    print(f"\n{files} cached driving routes in {OSRM_CACHE_DIR}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
