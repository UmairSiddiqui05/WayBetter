"""`.env.example` is the environment contract — keep it exhaustive.

CLAUDE.md requires every configurable value to come from the environment and
`.env.example` to stay current. These tests fail the build when a `Settings`
field or a Compose interpolation has no documented template entry, which is the
failure mode that makes a "fresh clone + cp .env.example .env" start-up break.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_EXAMPLE = REPO_ROOT / ".env.example"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"

# Compose supplies these to containers itself; they are not process settings.
COMPOSE_ONLY_KEYS = frozenset(
    {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "API_PORT",
        "POSTGRES_PORT",
        "REDIS_PORT",
        "OTP_PORT",
        "OTP_MAX_HEAP",
    }
)


def _documented_keys() -> set[str]:
    keys: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_every_setting_has_a_template_entry() -> None:
    documented = _documented_keys()
    missing = {name.upper() for name in Settings.model_fields} - documented

    assert not missing, f"Add these to .env.example: {sorted(missing)}"


def test_every_compose_variable_has_a_template_entry() -> None:
    documented = _documented_keys()
    referenced = set(
        re.findall(r"\$\{([A-Z][A-Z0-9_]*)(?::-[^}]*)?\}", COMPOSE_FILE.read_text(encoding="utf-8"))
    )
    missing = referenced - documented

    assert not missing, f"docker-compose.yml uses undocumented variables: {sorted(missing)}"


def test_template_documents_nothing_unused() -> None:
    """A stale key in the template is a trap for the next person setting up."""
    documented = _documented_keys()
    known = {name.upper() for name in Settings.model_fields} | COMPOSE_ONLY_KEYS
    orphans = documented - known

    assert not orphans, (
        "These .env.example keys match no Settings field and no Compose variable: "
        f"{sorted(orphans)}"
    )


def test_template_carries_no_real_looking_credentials() -> None:
    """Placeholders only — the CI secret guard is the second line of defence."""
    content = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert not re.search(r"(sk-[A-Za-z0-9]{20,}|AIza[A-Za-z0-9_-]{30,})", content)
