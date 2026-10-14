"""External services behind interfaces (N-04).

Business logic depends only on the protocols in `base.py`. Tonight's demo adapters are
OSRM (driving) and a direct GTFS reader (transit); the production plan swaps in Mapbox
and OpenTripPlanner by writing new adapters, without touching the trip service.
"""

from app.providers.base import (
    DriveRoute,
    DriveStep,
    DrivingProvider,
    LatLon,
    ProviderError,
    TransitProvider,
    TransitTrip,
)

__all__ = [
    "DriveRoute",
    "DriveStep",
    "DrivingProvider",
    "LatLon",
    "ProviderError",
    "TransitProvider",
    "TransitTrip",
]
