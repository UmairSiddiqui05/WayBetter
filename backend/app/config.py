"""Application settings.

Every value comes from the process environment (or a local `.env` in development).
Nothing here carries a real credential default, and secrets are wrapped in
``SecretStr`` so they cannot leak into logs or tracebacks by accident (CLAUDE.md
"Secrets"; N-05). Keep `.env.example` in sync with every field added here.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The API contract (docs/api-spec.yaml) declares `servers: [{url: /api/v1}]`.
# Every contract endpoint is mounted under this prefix; ops endpoints are not
# part of the contract and live at the root (see app/api/health.py).
API_V1_PREFIX = "/api/v1"

PLACEHOLDER_SECRETS = frozenset({"change-me", "placeholder", ""})


class Environment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class Settings(BaseSettings):
    """Runtime configuration, read from the environment only."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ---
    environment: Environment = Environment.DEVELOPMENT
    api_base_url: str = "http://localhost:8000"
    session_token_secret: SecretStr = SecretStr("change-me")

    # --- Datastores ---
    database_url: str = "postgresql+psycopg://waybetter:waybetter@localhost:5432/waybetter"
    redis_url: str = "redis://localhost:6379/0"

    # --- Routing engines ---
    otp_base_url: str = "http://localhost:8080"
    region_config_path: str = "data/regions/nyc-metro.yaml"

    # --- External providers (server-side only; never shipped to clients, N-05) ---
    mapbox_access_token: SecretStr = SecretStr("")
    mapbox_public_token: str = ""
    maptiler_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")

    # --- Transit agency feeds ---
    njt_developer_username: str = ""
    njt_developer_password: SecretStr = SecretStr("")
    mta_api_key: SecretStr = SecretStr("")

    # --- Web client ---
    # Comma-separated origins allowed to call the API from a browser. Empty in
    # production-by-default posture; dev/staging set it explicitly.
    cors_allow_origins: str = ""

    # --- Observability ---
    sentry_dsn: str = ""
    provider_spend_alert_email: str = ""
    log_level: str = "INFO"

    # --- Infra probe tuning (readiness checks; see app/health/probes.py) ---
    probe_timeout_seconds: float = Field(default=2.0, gt=0, le=30)

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def _reject_placeholder_secrets_in_production(self) -> Settings:
        """Fail fast rather than run production on the `.env.example` placeholders."""
        if self.environment is not Environment.PRODUCTION:
            return self
        if self.session_token_secret.get_secret_value().strip() in PLACEHOLDER_SECRETS:
            raise ValueError(
                "SESSION_TOKEN_SECRET must be set to a real value when ENVIRONMENT=production"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton (FastAPI dependency-injectable)."""
    return Settings()
