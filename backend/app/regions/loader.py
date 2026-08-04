"""Region config loading.

The path comes from `REGION_CONFIG_PATH` (environment, per CLAUDE.md) and is
resolved against the repo root so the same value works whether the API runs on
the host or in a container.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings
from app.regions.schema import RegionConfig

REPO_ROOT = Path(__file__).resolve().parents[3]


class RegionConfigError(RuntimeError):
    """Raised when a region file is missing or does not satisfy the schema."""


def resolve_region_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def load_region_config(path: str | Path) -> RegionConfig:
    """Parse and validate a single region file. Never partially applies a bad file."""
    resolved = resolve_region_path(path)
    if not resolved.is_file():
        raise RegionConfigError(f"region config not found: {resolved}")

    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegionConfigError(f"region config is not valid YAML: {resolved}") from exc

    if not isinstance(raw, dict):
        raise RegionConfigError(f"region config must be a mapping: {resolved}")

    try:
        return RegionConfig.model_validate(raw)
    except ValueError as exc:
        raise RegionConfigError(f"region config failed validation ({resolved}): {exc}") from exc


@lru_cache(maxsize=1)
def get_region_config() -> RegionConfig:
    """The configured region, loaded once per process."""
    return load_region_config(get_settings().region_config_path)
