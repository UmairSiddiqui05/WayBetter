"""Settings behaviour: environment-only config, secrets that do not leak (N-05)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_secrets_are_not_exposed_by_repr() -> None:
    settings = Settings(environment="test", session_token_secret="super-secret-value")  # type: ignore[arg-type]

    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.session_token_secret)
    assert settings.session_token_secret.get_secret_value() == "super-secret-value"


def test_production_rejects_placeholder_session_secret() -> None:
    with pytest.raises(ValidationError, match="SESSION_TOKEN_SECRET"):
        Settings(environment="production", session_token_secret="change-me")  # type: ignore[arg-type]


def test_production_accepts_a_real_session_secret() -> None:
    settings = Settings(environment="production", session_token_secret="0f3c-not-a-placeholder")  # type: ignore[arg-type]

    assert settings.is_production is True


def test_settings_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://example.invalid:6379/3")
    monkeypatch.setenv("REGION_CONFIG_PATH", "data/regions/other.yaml")

    settings = Settings(environment="test")  # type: ignore[arg-type]

    assert settings.redis_url == "redis://example.invalid:6379/3"
    assert settings.region_config_path == "data/regions/other.yaml"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        ("http://localhost:3000", ["http://localhost:3000"]),
        (" http://a.test , http://b.test ", ["http://a.test", "http://b.test"]),
    ],
)
def test_cors_origins_parsing(raw: str, expected: list[str]) -> None:
    settings = Settings(environment="test", cors_allow_origins=raw)  # type: ignore[arg-type]

    assert settings.cors_origins == expected
