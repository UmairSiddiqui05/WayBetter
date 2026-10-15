"""Turns a place in the user's words into a point we can route from — or says it can't.

Order: verified corridor places (human-checked facts, matched by name or alias, allowing
small typos), then — when the words name something we don't know *in* a known town — that
town, marked approximate with a question. Never silently picks a different place: no match
means "not found" and a clarifying question (N-02).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from app.trips.corridor import Corridor, Place
from app.trips.models import LatLng, Provenance

Role = Literal["origin", "destination"]

FUZZY_MIN_RATIO = 0.88
"""How close a misspelling must be to a known name ("javitz center" ~ "javits center")."""

_RIGHT_QUOTE = chr(0x2019)  # curly apostrophe, as phones type it
# Words that add no identity to a name: "Javits Center NYC" is still the Javits Center.
_FILLER = frozenset(
    {"nj", "ny", "nyc", "new", "jersey", "york", "city", "manhattan", "please", "area"}
)
# "<something> in <town>", "<something>, <town>", "<something> near <town>"
_IN_TOWN = re.compile(r"^(?P<what>.+?)\s*(?:,|\bin\b|\bnear\b|\bby\b)\s*(?P<town>[^,]+?)\s*$", re.I)


@dataclass(frozen=True, slots=True)
class Resolution:
    point: LatLng | None
    provenance: Provenance
    value_label: str
    note: str
    question: str | None = None
    """Set when the user should confirm or correct this place."""
    place: Place | None = None


def normalize(text: str) -> str:
    """Lowercase, no punctuation or apostrophes, no leading article, single spaces."""
    lowered = text.lower().replace(_RIGHT_QUOTE, "").replace("'", "")
    words = re.sub(r"[^a-z0-9]+", " ", lowered).split()
    while words and words[0] in {"the", "a", "an"}:
        words = words[1:]
    return " ".join(words)


def names_of(place: Place) -> set[str]:
    """Label without its parenthetical detail ("Times Square (1540 Broadway)" -> "times
    square"), the id with dashes as spaces, the town, and every alias — all normalized."""
    names = {normalize(place.label.split("(")[0]), normalize(place.id.replace("-", " "))}
    names.update(normalize(a) for a in place.aliases)
    if place.town:
        names.add(normalize(place.town))
    return {n for n in names if n}


def _matches(wanted: str, names: set[str]) -> bool:
    if wanted in names:
        return True
    core = " ".join(w for w in wanted.split() if w not in _FILLER)
    if core and core in names:
        return True
    return any(SequenceMatcher(None, wanted, n).ratio() >= FUZZY_MIN_RATIO for n in names)


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
            if _matches(wanted, names_of(place)):
                return place
        return None

    def split_town(self, text: str) -> tuple[str, str] | None:
        """("DeLucia's Brick Oven Pizza", "raritan") for "DeLucia's Brick Oven Pizza in raritan"."""
        if m := _IN_TOWN.match(text.strip()):
            return m["what"].strip(), m["town"].strip()
        return None

    def town_place(self, town: str) -> Place | None:
        wanted = normalize(town)
        for place in self._corridor.origins:
            if place.town and _matches(wanted, {normalize(place.town), *names_of(place)}):
                return place
        return None

    def resolve(self, text: str | None, role: Role) -> Resolution:
        if not text or not normalize(text):
            return not_given(role)
        if place := self.verified(text, role):
            return verified_resolution(text, place)
        if (parts := self.split_town(text)) and (place := self.verified(parts[0], role)):
            return verified_resolution(text, place)
        if parts and (town := self.town_place(parts[1])):
            return approximate_town(parts[0], town)
        return not_found(text)


def _attribution(place: Place) -> str:
    return " Coordinates: © OpenStreetMap contributors (ODbL)." if place.source else ""


def not_given(role: Role) -> Resolution:
    return Resolution(
        point=None,
        provenance=Provenance.UNKNOWN,
        value_label="not given",
        note=f"No {role} found in your words",
        question=f"Where are you {'starting from' if role == 'origin' else 'going'}?",
    )


def verified_resolution(text: str, place: Place) -> Resolution:
    return Resolution(
        point=LatLng(lat=place.lat, lng=place.lng, label=place.label),
        provenance=Provenance.AI_GENERATED,
        value_label=place.label,
        note=f'Read "{text}" from your words; matched the verified place {place.label}.'
        + _attribution(place),
        place=place,
    )


def approximate_town(what: str, town: Place) -> Resolution:
    town_name = town.town or town.label
    label = f"{town.label} (approximate for {what})"
    return Resolution(
        point=LatLng(lat=town.lat, lng=town.lng, label=label),
        provenance=Provenance.ESTIMATED,
        value_label=label,
        note=f'Approximate: I don\'t know "{what}" itself, so I used {town.label}, a verified '
        f"point in {town_name}. Drive times from there are close but not exact."
        + _attribution(town),
        question=(
            f'I don\'t know "{what}" exactly, so I started from {town.label}. '
            "Is that close enough, or what's the street address?"
        ),
        place=town,
    )


def not_found(text: str) -> Resolution:
    return Resolution(
        point=None,
        provenance=Provenance.UNKNOWN,
        value_label=f'"{text}" (not found)',
        note=f'"{text}" is not a place I know on this corridor',
        question=f'I don\'t know "{text}" yet. Which town or landmark is it near?',
    )
