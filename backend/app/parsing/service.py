"""ParsedTrip -> a draft TripSearchRequest, plus "Here's what I understood" (F-08, N-02).

The parser (LLMProvider) only reads words. Places, dates, defaults and what is still
missing are decided here, by the same code whichever parser ran.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog

from app.parsing.models import (
    AiParseResponse,
    InterpretationItem,
    ParsedTrip,
    TripSearchDraft,
)
from app.parsing.places import PlaceResolver
from app.providers.base import LLMProvider, ProviderError
from app.trips.corridor import Corridor
from app.trips.models import Preferences, Provenance, VehicleProfile

log = structlog.get_logger(__name__)

_FROM_WORDS = "Read from your words"
_PRIORITY_LABELS = {
    "cheapest": "Cheapest first",
    "fastest": "Fastest first",
    "best_overall": "Best overall",
}


def clock(hhmm: str) -> str:
    """ "18:00" -> "6:00 PM"."""
    hour, minute = (int(p) for p in hhmm.split(":"))
    suffix = "AM" if hour < 12 else "PM"
    return f"{(hour % 12) or 12}:{minute:02d} {suffix}"


def _leave_label(at: datetime, hhmm: str) -> str:
    return f"Leave {at:%a %b} {at.day}, {clock(hhmm)}"


def _minutes(hhmm: str) -> int:
    hour, minute = (int(p) for p in hhmm.split(":"))
    return hour * 60 + minute


class TripParseService:
    def __init__(
        self,
        parser: LLMProvider,
        fallback: LLMProvider,
        resolver: PlaceResolver,
        corridor: Corridor,
        timezone: ZoneInfo,
    ) -> None:
        self._parser = parser
        self._fallback = fallback
        self._resolver = resolver
        self._corridor = corridor
        self._tz = timezone

    def parse(self, text: str, now: datetime) -> AiParseResponse:
        parser_note = None
        try:
            parsed = self._parser.parse_trip(text)
            used = self._parser.name
        except ProviderError as exc:
            log.warning("trip_parser_fallback", parser=self._parser.name, error=str(exc))
            parsed = self._fallback.parse_trip(text)
            used = self._fallback.name
            parser_note = f"{self._parser.name} unavailable ({exc}); used the {used} parser"
        return self.interpret(parsed, now, parser=used, parser_note=parser_note)

    def _depart_date(self, hhmm: str, now: datetime) -> datetime:
        """Today if that time is still ahead on a weekday, otherwise the next weekday."""
        local = now.astimezone(self._tz)
        hour, minute = (int(p) for p in hhmm.split(":"))
        at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        while at <= local or at.weekday() >= 5:
            at = (at + timedelta(days=1)).replace(hour=hour, minute=minute)
        return at

    def interpret(
        self, parsed: ParsedTrip, now: datetime, parser: str, parser_note: str | None = None
    ) -> AiParseResponse:
        items: list[InterpretationItem] = []
        missing: list[str] = []
        questions: list[str] = []

        points = {}
        for role, words in (
            ("origin", parsed.origin_text),
            ("destination", parsed.destination_text),
        ):
            res = self._resolver.resolve(words, role)  # type: ignore[arg-type]
            points[role] = res.point
            items.append(
                InterpretationItem(
                    field=role,
                    value_label=res.value_label,
                    provenance=res.provenance,
                    note=res.note,
                )
            )
            if res.point is None:
                missing.append(role)
            if res.question:
                questions.append(res.question)

        # When: leave-at time (words or corridor default), or arrive-by (not supported yet).
        target_time: datetime | None = None
        if parsed.arrive_by_time:
            missing.append("target_time")
            items.append(
                InterpretationItem(
                    field="target_time",
                    value_label=f"Arrive by {clock(parsed.arrive_by_time)}",
                    provenance=Provenance.UNKNOWN,
                    note="Arrive-by planning isn't supported yet; a search needs a departure time",
                )
            )
            questions.append(
                f"I can't plan to arrive by {clock(parsed.arrive_by_time)} yet. "
                "What time would you like to leave?"
            )
            depart_hhmm = None
        elif parsed.leave_time:
            depart_hhmm = parsed.leave_time
            target_time = self._depart_date(depart_hhmm, now)
            items.append(
                InterpretationItem(
                    field="target_time",
                    value_label=_leave_label(target_time, depart_hhmm),
                    provenance=Provenance.AI_GENERATED,
                    note=f"{_FROM_WORDS}; date is the next weekday at that time",
                )
            )
        else:
            depart_hhmm = self._corridor.commute.default_departure_time
            target_time = self._depart_date(depart_hhmm, now)
            items.append(
                InterpretationItem(
                    field="target_time",
                    value_label=_leave_label(target_time, depart_hhmm),
                    provenance=Provenance.ESTIMATED,
                    is_default=True,
                    note="Default: you didn't say when, so a typical morning commute departure",
                )
            )

        return_time = None
        if parsed.home_time:
            if depart_hhmm and _minutes(parsed.home_time) <= _minutes(depart_hhmm):
                missing.append("return_time")
                items.append(
                    InterpretationItem(
                        field="return_time",
                        value_label=f"Head home {clock(parsed.home_time)}",
                        provenance=Provenance.UNKNOWN,
                        note="Not after the departure, so it can't be the same-day trip home",
                    )
                )
                questions.append("What time do you head home? It must be after you leave.")
            else:
                return_time = parsed.home_time
                items.append(
                    InterpretationItem(
                        field="return_time",
                        value_label=f"Head home {clock(parsed.home_time)}",
                        provenance=Provenance.AI_GENERATED,
                        note=_FROM_WORDS,
                    )
                )
        else:
            default_home = self._corridor.commute.default_return_time
            items.append(
                InterpretationItem(
                    field="return_time",
                    value_label=f"Head home {clock(default_home)}",
                    provenance=Provenance.ESTIMATED,
                    is_default=True,
                    note="Default: the corridor's usual evening departure",
                )
            )

        sort_mode = parsed.priority or "best_overall"
        items.append(
            InterpretationItem(
                field="preferences.sort_mode",
                value_label=_PRIORITY_LABELS[sort_mode],
                provenance=Provenance.AI_GENERATED if parsed.priority else Provenance.ESTIMATED,
                is_default=parsed.priority is None,
                note=_FROM_WORDS if parsed.priority else "Default: balances time and cost",
            )
        )
        toll = parsed.toll_payment or "ezpass"
        items.append(
            InterpretationItem(
                field="vehicle_profile.toll_payment",
                value_label="E-ZPass" if toll == "ezpass" else "Cash / toll by mail",
                provenance=Provenance.AI_GENERATED if parsed.toll_payment else Provenance.ESTIMATED,
                is_default=parsed.toll_payment is None,
                note=_FROM_WORDS if parsed.toll_payment else "Default: most commuters use E-ZPass",
            )
        )

        draft = TripSearchDraft(
            origin=points["origin"],
            destination=points["destination"],
            time_mode="leave_at",
            target_time=target_time,
            return_time=return_time,
            preferences=Preferences(sort_mode=sort_mode),
            vehicle_profile=VehicleProfile(toll_payment=toll),
        )
        return AiParseResponse(
            draft=draft,
            missing_fields=missing,
            clarifying_question=questions[0] if questions else None,
            interpretation=items,
            parser=parser,
            parser_note=parser_note,
        )
