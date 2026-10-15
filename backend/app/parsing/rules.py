"""Deterministic rules parser — an LLMProvider adapter with no model behind it.

Always available, instant, and testable: it is the fallback whenever the local model is
not running, times out, or returns something invalid. It only fills ParsedTrip.
"""

from __future__ import annotations

import re
from typing import Literal

from app.parsing.models import ParsedTrip

_TIME = r"(?P<h>\d{1,2})(?::(?P<m>[0-5]\d))?\s*(?P<ap>[ap]\.?\s?m\.?)?(?=$|[\s,.;!?)])"

_HOME = re.compile(
    r"\b(?:head(?:ing)?\s+(?:back\s+)?home|go(?:ing)?\s+(?:back\s+)?home|get(?:ting)?\s+home|"
    r"(?:back\s+)?home|leav(?:e|ing)\s+(?:work|the\s+office)|return(?:ing)?)\s+"
    r"(?:at\s+|around\s+|by\s+|about\s+)?" + _TIME,
    re.IGNORECASE,
)
_ARRIVE_BY = re.compile(
    r"\b(?:(?:arrive|get\s+there|be\s+there|be\s+in|get\s+in)\s+)?(?:by|before|no\s+later\s+than)\s+"
    + _TIME,
    re.IGNORECASE,
)
_LEAVE = re.compile(
    r"\b(?:(?:leav(?:e|ing)|depart(?:ing)?|head(?:ing)?\s+out|start(?:ing)?)\s+(?:at\s+|around\s+|about\s+)?"
    r"|(?:at|around)\s+)" + _TIME,
    re.IGNORECASE,
)
_STOP = (
    r"(?=\s*(?:[,.;!?]|\band\b|\b(?:at|by|around|before)\s+\d|\bleav|\bhead|\bhome\b|\barriv"
    r"|\bi\s+(?:want|need|have|would|'d)|\bcheap|\bfast|\bquick|\bwith\b|\busing\b"
    r"|\bwhat\b|\bhow\b|\btomorrow\b|\btoday\b|$))"
)
_FROM_TO = re.compile(r"\bfrom\s+(?P<o>.+?)\s+to\s+(?P<d>.+?)" + _STOP, re.IGNORECASE)
_TO_FROM = re.compile(r"\bto\s+(?P<d>.+?)\s+from\s+(?P<o>.+?)" + _STOP, re.IGNORECASE)

_CHEAP = re.compile(
    r"\bcheap(?:est|ly|er)?\b|\bsav(?:e|ing)\s+(?:some\s+)?money\b|\bleast\s+expensive\b"
    r"|\blowest\s+cost\b|\bbudget\b|\binexpensive\b|\baffordabl",
    re.IGNORECASE,
)
_FAST = re.compile(
    r"\bfast(?:est|er)?\b|\bquick(?:est|ly|er)?\b|\basap\b|\bas\s+soon\s+as\b|\bshortest\b",
    re.IGNORECASE,
)
_EZPASS = r"e[\s-]?z[\s-]?pass"
_CASH = re.compile(
    rf"\bcash\b|\bno\s+{_EZPASS}|\bdon'?t\s+have\s+(?:an?\s+)?{_EZPASS}"
    rf"|\bwithout\s+(?:an?\s+)?{_EZPASS}|\btolls?\s+by\s+mail\b",
    re.IGNORECASE,
)
_HAS_EZPASS = re.compile(rf"\b{_EZPASS}\b", re.IGNORECASE)


def _hhmm(match: re.Match[str], no_meridiem_pm_below: int) -> str:
    """24-hour "HH:MM". Without am/pm, hours 1..(no_meridiem_pm_below - 1) read as PM."""
    hour, minute = int(match["h"]), int(match["m"] or 0)
    ap = (match["ap"] or "").replace(".", "").replace(" ", "").lower()
    if ap == "pm" and hour < 12:
        hour += 12
    elif ap == "am" and hour == 12:
        hour = 0
    elif not ap and 1 <= hour < no_meridiem_pm_below:
        hour += 12
    return f"{hour % 24:02d}:{minute:02d}"


def _clean_place(text: str) -> str | None:
    cleaned = text.strip(" \t'\"")
    return cleaned or None


class RulesParser:
    name = "rules"

    def parse_trip(self, text: str) -> ParsedTrip:
        rest = text
        home_time: str | None = None
        arrive_by: str | None = None
        leave_time: str | None = None

        if home := _HOME.search(rest):
            home_time = _hhmm(home, no_meridiem_pm_below=12)  # "home at 6" = 6 PM
            rest = rest[: home.start()] + " " + rest[home.end() :]
        if arrive := _ARRIVE_BY.search(rest):
            arrive_by = _hhmm(arrive, no_meridiem_pm_below=5)
            rest = rest[: arrive.start()] + " " + rest[arrive.end() :]
        if leave := _LEAVE.search(rest):
            leave_time = _hhmm(leave, no_meridiem_pm_below=5)  # "leave at 7" = 7 AM

        origin = destination = None
        if places := _FROM_TO.search(text) or _TO_FROM.search(text):
            origin, destination = _clean_place(places["o"]), _clean_place(places["d"])

        priority: Literal["cheapest", "fastest"] | None = None
        cheap, fast = _CHEAP.search(text), _FAST.search(text)
        if cheap and (not fast or cheap.start() < fast.start()):
            priority = "cheapest"
        elif fast:
            priority = "fastest"

        toll: Literal["ezpass", "cash"] | None = (
            "cash" if _CASH.search(text) else "ezpass" if _HAS_EZPASS.search(text) else None
        )

        return ParsedTrip(
            origin_text=origin,
            destination_text=destination,
            priority=priority,
            leave_time=leave_time,
            arrive_by_time=arrive_by,
            home_time=home_time,
            toll_payment=toll,
        )
