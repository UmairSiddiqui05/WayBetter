"""Turns a place in the user's words into a point we can route from — or says it can't.

Order: verified corridor places (human-checked facts) first. Never silently picks a
different place: no match means "not found" and a clarifying question (N-02).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.trips.corridor import Corridor, Place
from app.trips.models import LatLng, Provenance

Role = Literal["origin", "destination"]


@dataclass(frozen=True, slots=True)
class Resolution:
    point: LatLng | None
    provenance: Provenance
    value_label: str
    note: str
    question: str | None = None
    """Set when the user should confirm or correct this place."""


def normalize(text: str) -> str:
    """Lowercase, no punctuation or apostrophes, no leading article, single spaces."""
    lowered = text.lower().replace("\u2019", "").replace("'", "")
    words = re.sub(r"[^a-z0-9]+", " ", lowered).split()
    while words and words[0] in {"the", "a", "an"}:
        words = words[1:]
    return " ".join(words)


def _names(place: Place) -> list[str]:
    """The label without its parenthetical detail ("Times Square (1540 Broadway)" ->
    "times square"), plus the id with dashes as spaces."""
    base = place.label.split("(")[0]
    return [normalize(base), normalize(place.id.replace("-", " "))]


class PlaceResolver:
    def __init__(self, corridor: Corridor) -> None:
        self._corridor = corridor

    def _candidates(self, role: Role) -> tuple[Place, ...]:
        c = self._corridor
        return (*c.origins, *c.destinations) if role == "origin" else (*c.destinations, *c.origins)

    def verified(self, text: str, role: Role) -> Place | None:
        wanted = normalize(text)
        if not wanted:
            return None
        for place in self._candidates(role):
            if wanted in _names(place):
                return place
        return None

    def resolve(self, text: str | None, role: Role) -> Resolution:
        if not text or not normalize(text):
            return Resolution(
                point=None,
                provenance=Provenance.UNKNOWN,
                value_label="not given",
                note=f"No {role} found in your words",
                question=f"Where are you {'starting from' if role == 'origin' else 'going'}?",
            )
        if place := self.verified(text, role):
            return Resolution(
                point=LatLng(lat=place.lat, lng=place.lng, label=place.label),
                provenance=Provenance.AI_GENERATED,
                value_label=place.label,
                note=f'Read "{text}" from your words; matched the verified place {place.label}',
            )
        return Resolution(
            point=None,
            provenance=Provenance.UNKNOWN,
            value_label=f'"{text}" (not found)',
            note=f'"{text}" is not a place I know on this corridor',
            question=(f'I don\'t know "{text}" yet. Which town or landmark is it near?'),
        )
