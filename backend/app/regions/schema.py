"""Region configuration schema.

Regions are data, not code (N-03, D-08). A region config names its bounding box,
timezone, feed registry, city-driving zones, and the data files that carry its
fares, tolls, and parking — so a new metro is a new config plus data plus
per-agency rule modules, with no logic change.

Two rules this schema enforces structurally:

- **No fare or toll values live here** (F-12, F-13). The config only *points at*
  effective-dated data files.
- **Every feed records its licence and whether that licence has been confirmed
  by a human** (N-09). `license_verified` defaults to False, so an unchecked
  feed is visibly unchecked rather than silently assumed fine.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    """Unknown keys are an error: a typo in a region file must not fail silently."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class TransitMode(StrEnum):
    SUBWAY = "subway"
    COMMUTER_RAIL = "commuter_rail"
    RAPID_TRANSIT = "rapid_transit"
    BUS = "bus"
    FERRY = "ferry"


class FeedFormat(StrEnum):
    GTFS = "gtfs"
    GTFS_RT = "gtfs_rt"


class BoundingBox(StrictModel):
    """Request-validation boundary. Out-of-box requests are rejected before any
    paid provider call (N-05, fixture E-04)."""

    min_lat: float = Field(ge=-90, le=90)
    min_lng: float = Field(ge=-180, le=180)
    max_lat: float = Field(ge=-90, le=90)
    max_lng: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def _ordered(self) -> BoundingBox:
        if self.min_lat >= self.max_lat:
            raise ValueError("min_lat must be less than max_lat")
        if self.min_lng >= self.max_lng:
            raise ValueError("min_lng must be less than max_lng")
        return self

    def contains(self, lat: float, lng: float) -> bool:
        return self.min_lat <= lat <= self.max_lat and self.min_lng <= lng <= self.max_lng


class FeedLicense(StrictModel):
    """Provenance for a data source (N-09). No feed is used without one."""

    name: str
    url: str | None = None
    attribution: str | None = None
    notes: str | None = None
    verified: bool = False
    """True only once a human has read the terms and confirmed they permit this use.
    Unverified is the honest default — an agent must never assert it."""


class TokenAuth(StrictModel):
    """Two-step credentialed download: POST the portal credentials to `token_url`,
    then POST the returned token to the feed `url`. Endpoint shapes are data so a
    second agency with the same pattern is config, not code (N-03)."""

    token_url: str
    username_field: str
    password_field: str
    token_response_field: str
    token_form_field: str


PLACEHOLDER_CREDENTIAL = "placeholder"
"""The `.env.example` stand-in value; treated the same as an unset variable."""


class FeedSource(StrictModel):
    """One GTFS (or GTFS-RT) feed in the region's registry."""

    feed_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    agency_name: str
    agency_ids: tuple[str, ...] = ()
    """`agency_id` values as they appear in the feed's agency.txt. Populated after
    first download; used to key canonical station IDs (N-03)."""
    modes: tuple[TransitMode, ...]
    format: FeedFormat = FeedFormat.GTFS
    url: str | None = None
    license: FeedLicense
    enabled: bool = True
    requires_credentials: bool = False
    credential_env: tuple[str, ...] = ()
    """Environment variable names holding this feed's credentials. Never the
    credentials themselves — those come from the environment (CLAUDE.md)."""
    auth: TokenAuth | None = None
    """How credentials are exchanged for the archive. With `auth`, `credential_env`
    is `(username_var, password_var)`."""
    blocked_reason: str | None = None
    """Set when a feed is known-unfetchable right now (missing credentials,
    unreachable host). Keeps the registry honest instead of silently short."""

    @model_validator(mode="after")
    def _credentialed_feeds_name_their_env_vars(self) -> FeedSource:
        if self.requires_credentials and not self.credential_env:
            raise ValueError(
                f"feed {self.feed_id!r} requires credentials but names no credential_env vars"
            )
        if self.enabled and not self.url and not self.requires_credentials:
            raise ValueError(f"feed {self.feed_id!r} is enabled but has no url")
        if self.auth and (not self.requires_credentials or len(self.credential_env) != 2):
            raise ValueError(
                f"feed {self.feed_id!r} has token auth, so it must require credentials "
                "and name exactly two credential_env vars (username, password)"
            )
        return self

    def has_credentials(self, env: Mapping[str, str]) -> bool:
        """True when every named credential variable holds a real value."""
        return all(
            env.get(var, "").strip() not in ("", PLACEHOLDER_CREDENTIAL)
            for var in self.credential_env
        )


class CityDrivingZone(StrictModel):
    """A polygon the `avoid_city_driving` filter tests driving legs against (F-07).

    The polygon itself lives in a GeoJSON file, not in this config — geometry is
    data, and PostGIS does the intersection.
    """

    zone_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str
    geojson_path: str


class DataFiles(StrictModel):
    """Pointers to effective-dated data files. Never values (F-12, F-13)."""

    fares_dir: str
    tolls_dir: str
    parking_dir: str
    vehicle_dir: str = "data/vehicle"
    emissions_dir: str = "data/emissions"


MAP_LINK_FIELDS = frozenset({"origin_lat", "origin_lng", "destination_lat", "destination_lng"})


class MapHandoff(StrictModel):
    """An "Open in <app>" link for a drive leg (F-17). The URL is a template so the app list and
    URL formats are configuration; the trip service only fills in the leg's two ends."""

    app_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    label: str
    url_template: str = Field(pattern=r"^https://")
    docs_url: str | None = None
    """Where the app documents this URL format."""

    @field_validator("url_template")
    @classmethod
    def _known_fields(cls, value: str) -> str:
        used = set(re.findall(r"{([^{}]*)}", value))
        if not used or not used <= MAP_LINK_FIELDS:
            raise ValueError(f"url_template may only use {sorted(MAP_LINK_FIELDS)}, got {used}")
        return value

    def url(self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> str:
        return self.url_template.format(
            origin_lat=f"{origin_lat:.5f}",
            origin_lng=f"{origin_lng:.5f}",
            destination_lat=f"{dest_lat:.5f}",
            destination_lng=f"{dest_lng:.5f}",
        )


class GraphBundle(StrictModel):
    """OTP graph + precompute + feed metadata deploy as one versioned unit (N-08)."""

    version: str | None = None
    path: str = "data/otp-graphs/current"


class RegionConfig(StrictModel):
    """The whole of what WayBetter knows about a region, before any data file is read."""

    region_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str
    timezone: str
    """IANA zone name. Every timestamp in the region resolves against it (E-02)."""
    bounding_box: BoundingBox
    default_parking_buffer_minutes: int = Field(ge=0, le=60)
    """Park-walk-to-platform allowance used by the arrive-by backward solve (F-05).
    A region default; per-station overrides live in the parking data."""
    feeds: tuple[FeedSource, ...]
    city_driving_zones: tuple[CityDrivingZone, ...] = ()
    data_files: DataFiles
    graph_bundle: GraphBundle = GraphBundle()
    map_handoff: tuple[MapHandoff, ...] = ()

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone {value!r}") from exc
        return value

    @model_validator(mode="after")
    def _unique_ids(self) -> RegionConfig:
        feed_ids = [f.feed_id for f in self.feeds]
        if len(feed_ids) != len(set(feed_ids)):
            raise ValueError("feed_id values must be unique within a region")
        zone_ids = [z.zone_id for z in self.city_driving_zones]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("zone_id values must be unique within a region")
        return self

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def enabled_feeds(self) -> tuple[FeedSource, ...]:
        return tuple(f for f in self.feeds if f.enabled)

    def fetchable_feeds(self, env: Mapping[str, str] | None = None) -> tuple[FeedSource, ...]:
        """Enabled, unblocked, and either keyless or holding its credentials."""
        env = os.environ if env is None else env
        return tuple(
            f
            for f in self.enabled_feeds()
            if f.url
            and not f.blocked_reason
            and (not f.requires_credentials or f.has_credentials(env))
        )
