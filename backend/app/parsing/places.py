"""Turns a place in the user's words into a point we can route from — or says it can't.

Order: (1) verified corridor places (human-checked facts, matched by name or alias, allowing
small typos); (2) the address lookup (GeocodingProvider), accepted only when the result's
name AND town agree with the words; (3) when the words name something we can't confirm *in*
a town we can find, that town, marked approximate, with a question. Never silently picks a
different place: a fuzzy search for "DeLucia's in Raritan" that returns a pizzeria in
Metuchen is rejected, not used. No match means "not found" and a question (N-02).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from app.providers.base import GeocodeResult, GeocodingProvider, ProviderError
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


_ABBREVIATIONS = {
    "street": "st", "avenue": "ave", "av": "ave", "road": "rd", "drive": "dr",
    "boulevard": "blvd", "place": "pl", "lane": "ln", "route": "rte", "highway": "hwy",
    "north": "n", "south": "s", "east": "e", "west": "w", "saint": "st", "mount": "mt",
    "centre": "center",
}  # fmt: skip
# Words that say what kind of place it is, not which one: two pizzerias share them.
_GENERIC = frozenset(
    {
        "pizza", "pizzeria", "restaurant", "diner", "cafe", "coffee", "bar", "grill", "deli",
        "bakery", "shop", "store", "brick", "oven", "kitchen", "house", "and", "of", "inc",
        "llc", "co", "market", "center", "convention", "station", "the", "s",
    }
)  # fmt: skip
_STATE_WORDS = frozenset(
    {"nj", "ny", "ct", "new", "jersey", "york", "usa", "us", "borough", "township", "twp", "of"}
)
TOKEN_MIN_RATIO = 0.85


def _tokens(text: str) -> list[str]:
    return [_ABBREVIATIONS.get(w, w) for w in normalize(text).split()]


def _has(token: str, pool: list[str]) -> bool:
    return any(
        token == p or SequenceMatcher(None, token, p).ratio() >= TOKEN_MIN_RATIO for p in pool
    )


def names_agree(found: str, said: str) -> bool:
    """The distinctive words of each name appear in the other ("DeLucia's" vs "DeLucia's Brick
    Oven Pizza" agree; "Brick Oven Pizza" vs "DeLucia's Brick Oven Pizza" do not)."""
    a, b = _tokens(found), _tokens(said)
    da, db = [w for w in a if w not in _GENERIC], [w for w in b if w not in _GENERIC]
    return bool(da and db) and all(_has(w, b) for w in da) and all(_has(w, a) for w in db)


def towns_agree(found: str | None, said: str) -> bool:
    if not found:
        return False
    a = " ".join(w for w in _tokens(found) if w not in _STATE_WORDS)
    b = " ".join(w for w in _tokens(said) if w not in _STATE_WORDS)
    return bool(a and b) and (a == b or SequenceMatcher(None, a, b).ratio() >= TOKEN_MIN_RATIO)


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
    def __init__(self, corridor: Corridor, geocoder: GeocodingProvider | None = None) -> None:
        self._corridor = corridor
        self._geocoder = geocoder

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
        parts = self.split_town(text)
        if parts and (place := self.verified(parts[0], role)):
            return verified_resolution(text, place)

        lookup_down = False
        if self._geocoder:
            try:
                if found := self._lookup(self._geocoder, text, parts):
                    if verified := self._corridor.place_near(found.point):
                        return verified_resolution(text, verified)  # its checked facts apply
                    if not parts:  # the words were a town itself: a point for an area
                        return geocoded_town(text, found, self._geocoder.attribution)
                    return geocoded(text, found, role, self._geocoder.attribution)
            except ProviderError:
                lookup_down = True

        if parts and (town := self.town_place(parts[1])):
            return approximate_town(parts[0], town, lookup_down)
        if parts and self._geocoder and not lookup_down:
            try:
                if found_town := self._lookup_town(self._geocoder, parts[1]):
                    return approximate_geocoded_town(
                        parts[0], found_town, self._geocoder.attribution
                    )
            except ProviderError:
                lookup_down = True
        return not_found(text, lookup_down)

    @staticmethod
    def _lookup(
        geocoder: GeocodingProvider, text: str, parts: tuple[str, str] | None
    ) -> GeocodeResult | None:
        """A result whose name and town both agree with the words — or None."""
        if parts:
            what, town = parts
            for r in geocoder.search(f"{what}, {town}"):
                name_ok = names_agree(r.name, what) or (
                    r.address_line is not None and names_agree(r.address_line, what)
                )
                if name_ok and any(towns_agree(t, town) for t in (r.town, *r.localities)):
                    return r
            return None
        # No town in the words: only a town itself can be confirmed ("Hoboken").
        for r in geocoder.search(text):
            if r.kind in {"place", "boundary"} and names_agree(r.name, text):
                return r
        return None

    @staticmethod
    def _lookup_town(geocoder: GeocodingProvider, town: str) -> GeocodeResult | None:
        for r in geocoder.search(town):
            if r.kind in {"place", "boundary"} and towns_agree(r.name, town):
                return r
        return None


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


_LOOKUP_DOWN = " Address lookup is unreachable right now, so only verified places are available."


def geocoded(text: str, found: GeocodeResult, role: Role, attribution: str) -> Resolution:
    label = (
        f"{found.name}, {found.town}" if found.town and found.town not in found.name else found.name
    )
    facts = (
        " Congestion-zone and parking facts are unknown for places outside the verified list."
        if role == "destination"
        else ""
    )
    return Resolution(
        point=LatLng(lat=found.point.lat, lng=found.point.lon, label=label),
        provenance=Provenance.AI_GENERATED,
        value_label=label,
        note=f'Read "{text}" from your words; found by address lookup: {found.display_name}.'
        f"{facts} {attribution}.",
    )


def geocoded_town(text: str, town: GeocodeResult, attribution: str) -> Resolution:
    label = f"{town.name} (town center)"
    return Resolution(
        point=LatLng(lat=town.point.lat, lng=town.point.lon, label=label),
        provenance=Provenance.ESTIMATED,
        value_label=label,
        note=f'Read "{text}" from your words; used the center of {town.display_name}, found by '
        f"address lookup. A street address would be more exact. {attribution}.",
    )


def approximate_geocoded_town(what: str, town: GeocodeResult, attribution: str) -> Resolution:
    label = f"{town.name} (town center, approximate for {what})"
    return Resolution(
        point=LatLng(lat=town.point.lat, lng=town.point.lon, label=label),
        provenance=Provenance.ESTIMATED,
        value_label=label,
        note=f'Approximate: I couldn\'t confirm "{what}" itself, so I used the center of '
        f"{town.display_name}. {attribution}.",
        question=(
            f'I couldn\'t find "{what}" exactly, so I started from the center of {town.name}. '
            "Is that close enough, or what's the street address?"
        ),
    )


def approximate_town(what: str, town: Place, lookup_down: bool = False) -> Resolution:
    town_name = town.town or town.label
    label = f"{town.label} (approximate for {what})"
    return Resolution(
        point=LatLng(lat=town.lat, lng=town.lng, label=label),
        provenance=Provenance.ESTIMATED,
        value_label=label,
        note=f'Approximate: I couldn\'t confirm "{what}" itself, so I used {town.label}, a '
        f"verified point in {town_name}. Drive times from there are close but not exact."
        + _attribution(town)
        + (_LOOKUP_DOWN if lookup_down else ""),
        question=(
            f'I couldn\'t find "{what}" exactly, so I started from {town.label}. '
            "Is that close enough, or what's the street address?"
        ),
        place=town,
    )


def not_found(text: str, lookup_down: bool = False) -> Resolution:
    return Resolution(
        point=None,
        provenance=Provenance.UNKNOWN,
        value_label=f'"{text}" (not found)',
        note=f'"{text}" is not a place I could find or confirm'
        + (_LOOKUP_DOWN if lookup_down else ""),
        question=(
            f"I couldn't find or confirm \"{text}\". What town is it in, or what's the street "
            "address?"
        ),
    )
