"""LLMProvider backed by a local model served by Ollama (D-19). Plain HTTP, no vendor SDK.

The model sees only the user's words and a JSON schema; it never sees prices, schedules or
routes and never produces them (D-11). Its answer is constrained to ParsedTrip's schema by
Ollama's `format` and validated again here with extra fields forbidden; anything else —
not running, slow, invalid JSON — is a ProviderError and the caller falls back to rules.
"""

from __future__ import annotations

import httpx
import structlog
from pydantic import ValidationError

from app.parsing.models import ParsedTrip
from app.providers.base import ProviderError

log = structlog.get_logger(__name__)

TIMEOUT_SECONDS = 20.0
KEEP_ALIVE = "30m"
"""How long Ollama keeps the model in memory after a call (a cold load takes ~5 s)."""

SYSTEM_PROMPT = """\
You read one trip request from a commuter in New Jersey / New York and fill a JSON object.
Rules:
- origin_text / destination_text: copy the start and end places exactly as the user wrote
  them, including business names and towns ("Joe's Diner in Raritan"). Do not correct,
  complete, or replace them with another place. null if not stated.
- priority: "cheapest" if they want to save money / go cheaply; "fastest" if they want speed;
  otherwise null.
- leave_time: when they want to leave, 24-hour "HH:MM". A bare morning hour like "7" is 07:00.
- arrive_by_time: if they must arrive by a time ("by 9", "be there before 8:30"), 24-hour.
- home_time: when they head home the same day, 24-hour; "home at 6" means 18:00.
- toll_payment: "cash" if they have no E-ZPass or pay cash; "ezpass" if they say E-ZPass.
- Anything not stated is null. Never invent places, times, prices, or routes.
"""


class OllamaProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        client: httpx.Client | None = None,
        timeout_s: float = TIMEOUT_SECONDS,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/api/chat"
        self._model = model
        self._client = client or httpx.Client(timeout=timeout_s)
        self.name = f"ollama:{model}"

    def parse_trip(self, text: str) -> ParsedTrip:
        body = {
            "model": self._model,
            "stream": False,
            "think": False,
            "keep_alive": KEEP_ALIVE,
            "format": ParsedTrip.model_json_schema(),
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        }
        try:
            response = self._client.post(self._url, json=body)
            response.raise_for_status()
            content = response.json()["message"]["content"]
        except httpx.TimeoutException as exc:
            raise ProviderError("local model timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"local model unreachable ({type(exc).__name__})") from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError("local model sent an unreadable response") from exc
        try:
            return ParsedTrip.model_validate_json(content)
        except ValidationError as exc:
            log.warning("ollama_invalid_output", errors=exc.error_count())
            raise ProviderError("local model output failed validation") from exc
