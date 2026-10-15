"""Models for POST /trip/ai-parse (docs/api-spec.yaml v0.3.0)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.trips.models import LatLng, Preferences, Provenance, VehicleProfile

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class ParsedTrip(BaseModel):
    """Everything a parser may say about a trip request — and nothing else (D-11).

    Places stay as the user's words; the server resolves them. Unknown fields are rejected,
    so a model that invents extra keys (a price, a route) fails validation instead of
    leaking through.
    """

    model_config = ConfigDict(extra="forbid")

    origin_text: str | None = Field(default=None, max_length=200)
    """Where the trip starts, in the user's words (e.g. "Raritan")."""
    destination_text: str | None = Field(default=None, max_length=200)
    priority: Literal["cheapest", "fastest", "least_driving"] | None = None
    """cheapest = lowest cost; fastest = least total door-to-door time; least_driving = least
    time behind the wheel (park and take the train)."""
    leave_time: str | None = Field(default=None, pattern=HHMM)
    """24-hour local "HH:MM" the user wants to leave."""
    arrive_by_time: str | None = Field(default=None, pattern=HHMM)
    """24-hour "HH:MM" the user must arrive by (not supported by search yet)."""
    home_time: str | None = Field(default=None, pattern=HHMM)
    """24-hour "HH:MM" the user heads home the same day."""
    toll_payment: Literal["ezpass", "cash"] | None = None


class AiParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1000)


class TripSearchDraft(BaseModel):
    """TripSearchRequest with the places nullable until they are resolved. Field names match
    TripSearchRequest exactly, so a complete draft posts to /trip/search unchanged."""

    origin: LatLng | None
    destination: LatLng | None
    time_mode: Literal["leave_now", "leave_at", "arrive_by"]
    target_time: datetime | None = None
    return_time: str | None = Field(default=None, pattern=HHMM)
    preferences: Preferences = Preferences()
    vehicle_profile: VehicleProfile = VehicleProfile()


class InterpretationItem(BaseModel):
    """One line of "Here's what I understood": a value and where it came from (N-02)."""

    field: str
    value_label: str
    provenance: Provenance
    is_default: bool = False
    """True when the user did not say this; the value is the app's default."""
    note: str | None = None


class PlaceChoice(BaseModel):
    """v0.7.0. One answer to the clarifying question: a place as text, for the From or To field."""

    field: Literal["origin", "destination"]
    text: str


class AiParseResponse(BaseModel):
    draft: TripSearchDraft
    missing_fields: list[str]
    clarifying_question: str | None
    choices: list[PlaceChoice] = []
    """v0.7.0. Places that answer `clarifying_question` (e.g. a street found in several towns);
    empty when the question has no fixed answers."""
    interpretation: list[InterpretationItem]
    parser: str
    """Which parser read the text: "rules", or "ollama:<model>" for the local model."""
    parser_note: str | None = None
    """Why the fallback parser was used, when it was."""


class PlaceLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200)
    """A place as typed: a verified place name, a street address, a business in a town."""
    role: Literal["origin", "destination"]


class PlaceLookupResponse(BaseModel):
    """One typed place, resolved by the same rules as /trip/ai-parse (verified places first,
    then the address lookup, then an approximate town). `place` is null when not found."""

    place: LatLng | None
    value_label: str
    provenance: Provenance
    note: str | None
    clarifying_question: str | None
    suggestions: list[str] = []
    """v0.5.0. When the words fit several places (e.g. a street in three towns): each as text
    the user can pick and send back. Empty otherwise."""
