from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
API_SPEC_PATH = REPO_ROOT / "docs" / "api-spec.yaml"


@pytest.fixture(scope="session", autouse=True)
def _test_environment() -> Iterator[None]:
    """Tests never touch a real datastore or provider; nothing here is a credential."""
    os.environ.setdefault("ENVIRONMENT", "test")
    yield


@pytest.fixture
def app(_test_environment: None) -> FastAPI:
    from app.config import Settings
    from app.main import create_app

    return create_app(Settings(environment="test"))  # type: ignore[arg-type]


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # No `with` block: lifespan startup/shutdown would open real datastore pools.
    yield TestClient(app)


@pytest.fixture(scope="session")
def api_contract() -> dict:
    return yaml.safe_load(API_SPEC_PATH.read_text(encoding="utf-8"))
