"""TransitProvider that reads a GTFS archive directly (demo stand-in for OTP, D-18).

Answers one question: the next scheduled direct trip between two stations on the same
train. Service days come from calendar.txt and/or calendar_dates.txt; GTFS times past
24:00 belong to the previous service day, so both today and yesterday are searched.
Every time it returns is `scheduled` (N-02) — no real-time data.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.providers.base import LatLon, TransitTrip
from app.providers.polyline import encode


@dataclass(frozen=True, slots=True)
class _StopTime:
    stop_id: str
    seq: int
    arrival_s: int
    departure_s: int
    pickup: bool
    drop_off: bool


@dataclass(frozen=True, slots=True)
class _Trip:
    trip_id: str
    route_id: str
    service_id: str
    headsign: str
    shape_id: str | None


def _seconds(value: str) -> int:
    hours, minutes, seconds = (int(part) for part in value.strip().split(":"))
    return hours * 3600 + minutes * 60 + seconds


class GtfsTransitProvider:
    def __init__(
        self,
        archive: Path,
        station_to_stop: dict[str, str],
        stop_coords: dict[str, LatLon],
        timezone: ZoneInfo,
    ) -> None:
        """`station_to_stop` maps canonical station IDs to this feed's stop_ids (N-03)."""
        self._archive = archive
        self._station_to_stop = station_to_stop
        self._stop_coords = stop_coords
        self._tz = timezone
        self._shapes: dict[str, list[LatLon]] = {}
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
            agencies = self._rows(zf, "agency.txt")
            routes = self._rows(zf, "routes.txt")
            self._route_names = {
                r["route_id"]: r.get("route_long_name") or r.get("route_short_name") or ""
                for r in routes
            }
            agency_names = {a.get("agency_id", ""): a["agency_name"] for a in agencies}
            default_agency = agencies[0]["agency_name"] if agencies else ""
            self._route_agency = {
                r["route_id"]: agency_names.get(r.get("agency_id", ""), default_agency)
                for r in routes
            }
            self._trips = {
                t["trip_id"]: _Trip(
                    trip_id=t["trip_id"],
                    route_id=t["route_id"],
                    service_id=t["service_id"],
                    headsign=t.get("trip_headsign", ""),
                    shape_id=t.get("shape_id") or None,
                )
                for t in self._rows(zf, "trips.txt")
            }
            self._stop_times: dict[str, list[_StopTime]] = defaultdict(list)
            self._trips_at_stop: dict[str, set[str]] = defaultdict(set)
            for row in self._rows(zf, "stop_times.txt"):
                if not row.get("arrival_time") or not row.get("departure_time"):
                    continue  # untimed stop; this reader only handles timepoints
                st = _StopTime(
                    stop_id=row["stop_id"],
                    seq=int(row["stop_sequence"]),
                    arrival_s=_seconds(row["arrival_time"]),
                    departure_s=_seconds(row["departure_time"]),
                    pickup=row.get("pickup_type", "0") in ("", "0", "2", "3"),
                    drop_off=row.get("drop_off_type", "0") in ("", "0", "2", "3"),
                )
                self._stop_times[row["trip_id"]].append(st)
                self._trips_at_stop[st.stop_id].add(row["trip_id"])
            for times in self._stop_times.values():
                times.sort(key=lambda s: s.seq)
            self._services_by_date: dict[str, set[str]] = defaultdict(set)
            if "calendar.txt" in names:
                self._load_calendar(self._rows(zf, "calendar.txt"))
            if "calendar_dates.txt" in names:
                for row in self._rows(zf, "calendar_dates.txt"):
                    if row["exception_type"] == "1":
                        self._services_by_date[row["date"]].add(row["service_id"])
                    else:
                        self._services_by_date[row["date"]].discard(row["service_id"])

    @staticmethod
    def _rows(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
        with zf.open(name) as handle:
            return list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")))

    def _load_calendar(self, rows: list[dict[str, str]]) -> None:
        weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
        for row in rows:
            day = datetime.strptime(row["start_date"], "%Y%m%d").date()
            end = datetime.strptime(row["end_date"], "%Y%m%d").date()
            while day <= end:
                if row[weekdays[day.weekday()]] == "1":
                    self._services_by_date[day.strftime("%Y%m%d")].add(row["service_id"])
                day += timedelta(days=1)

    def _service_midnight(self, service_day: date) -> datetime:
        # GTFS times count from "noon minus 12h" of the service day; equal to local
        # midnight except on DST-change days, which is acceptable for this demo reader.
        return datetime(service_day.year, service_day.month, service_day.day, tzinfo=self._tz)

    def next_trip(
        self, from_station: str, to_station: str, depart_after: datetime
    ) -> TransitTrip | None:
        from_stop = self._station_to_stop.get(from_station)
        to_stop = self._station_to_stop.get(to_station)
        if not from_stop or not to_stop:
            return None
        local = depart_after.astimezone(self._tz)
        candidates = self._trips_at_stop[from_stop] & self._trips_at_stop[to_stop]
        best: TransitTrip | None = None
        for service_day in (local.date() - timedelta(days=1), local.date()):
            active = self._services_by_date.get(service_day.strftime("%Y%m%d"), set())
            midnight = self._service_midnight(service_day)
            for trip_id in candidates:
                trip = self._trips[trip_id]
                if trip.service_id not in active:
                    continue
                times = self._stop_times[trip_id]
                board = next((s for s in times if s.stop_id == from_stop), None)
                alight = next((s for s in times if s.stop_id == to_stop), None)
                if not board or not alight or alight.seq <= board.seq:
                    continue
                if not board.pickup or not alight.drop_off:
                    continue
                departure = midnight + timedelta(seconds=board.departure_s)
                arrival = midnight + timedelta(seconds=alight.arrival_s)
                if departure < local:
                    continue
                # Earliest arrival wins (a later express can beat an earlier local);
                # on a tie, the later departure means less waiting on the platform.
                if best and (arrival, -departure.timestamp()) >= (
                    best.arrival,
                    -best.departure.timestamp(),
                ):
                    continue
                best = TransitTrip(
                    trip_id=trip_id,
                    agency=self._route_agency.get(trip.route_id, ""),
                    route_name=self._route_names.get(trip.route_id, ""),
                    headsign=trip.headsign,
                    from_station=from_station,
                    to_station=to_station,
                    departure=departure,
                    arrival=arrival,
                    shape_id=trip.shape_id,
                )
        return best

    def trip_polyline(self, trip: TransitTrip) -> str | None:
        points = self._shape(trip.shape_id) if trip.shape_id else []
        start = self._stop_coords.get(self._station_to_stop.get(trip.from_station, ""))
        end = self._stop_coords.get(self._station_to_stop.get(trip.to_station, ""))
        if not start or not end:
            return None
        if len(points) < 2:
            return encode([start, end])  # no shape in the feed: straight line, still honest
        i = min(range(len(points)), key=lambda k: _dist2(points[k], start))
        j = min(range(len(points)), key=lambda k: _dist2(points[k], end))
        segment = points[i : j + 1] if i <= j else list(reversed(points[j : i + 1]))
        return encode([start, *segment, end])

    def _shape(self, shape_id: str) -> list[LatLon]:
        if shape_id not in self._shapes:
            # shapes.txt can be tens of MB; read it once per unseen shape, keep only that one.
            rows: list[tuple[int, LatLon]] = []
            with zipfile.ZipFile(self._archive) as zf, zf.open("shapes.txt") as handle:
                for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8-sig")):
                    if row["shape_id"] == shape_id:
                        rows.append(
                            (
                                int(row["shape_pt_sequence"]),
                                LatLon(float(row["shape_pt_lat"]), float(row["shape_pt_lon"])),
                            )
                        )
            rows.sort(key=lambda r: r[0])
            self._shapes[shape_id] = [point for _, point in rows]
        return self._shapes[shape_id]


def _dist2(a: LatLon, b: LatLon) -> float:
    return (a.lat - b.lat) ** 2 + (a.lon - b.lon) ** 2
