"""Google encoded-polyline format (precision 5), shared by every adapter."""

from __future__ import annotations

from collections.abc import Iterable

from app.providers.base import LatLon


def _encode_value(value: int) -> str:
    value = ~(value << 1) if value < 0 else value << 1
    chunks = []
    while value >= 0x20:
        chunks.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chunks.append(chr(value + 63))
    return "".join(chunks)


def encode(points: Iterable[LatLon]) -> str:
    out: list[str] = []
    prev_lat = prev_lon = 0
    for point in points:
        lat, lon = round(point.lat * 1e5), round(point.lon * 1e5)
        out.append(_encode_value(lat - prev_lat))
        out.append(_encode_value(lon - prev_lon))
        prev_lat, prev_lon = lat, lon
    return "".join(out)


def decode(encoded: str) -> list[LatLon]:
    points: list[LatLon] = []
    index = lat = lon = 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        points.append(LatLon(lat / 1e5, lon / 1e5))
    return points
