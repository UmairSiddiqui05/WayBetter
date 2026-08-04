"""Ops health endpoints (A1 scaffold). Covers N-08 groundwork."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.health import ComponentHealth, HealthStatus, ReadinessReport


def test_healthz_is_dependency_free(client: TestClient) -> None:
    """Liveness must answer even with Postgres and Redis unreachable."""
    response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "waybetter-api"
    assert body["environment"] == "test"


def test_readyz_returns_200_when_required_components_are_up(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_readiness(_settings: object) -> ReadinessReport:
        return ReadinessReport(
            components=(
                ComponentHealth("postgres", HealthStatus.OK, detail="postgis 3.4.2"),
                ComponentHealth("redis", HealthStatus.OK),
                ComponentHealth("otp", HealthStatus.DOWN, detail="ConnectError", required=False),
            )
        )

    monkeypatch.setattr("app.api.health.check_readiness", fake_readiness)

    response = client.get("/readyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["components"]["postgres"]["detail"] == "postgis 3.4.2"


def test_readyz_returns_503_when_a_required_component_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_readiness(_settings: object) -> ReadinessReport:
        return ReadinessReport(
            components=(
                ComponentHealth("postgres", HealthStatus.DOWN, detail="ConnectionRefusedError"),
                ComponentHealth("redis", HealthStatus.OK),
            )
        )

    monkeypatch.setattr("app.api.health.check_readiness", fake_readiness)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_postgis_missing_is_not_ready() -> None:
    """PostGIS is required (city_driving_zone intersection, F-07) — degraded blocks readiness."""
    report = ReadinessReport(
        components=(
            ComponentHealth("postgres", HealthStatus.DEGRADED, detail="postgis not installed"),
            ComponentHealth("redis", HealthStatus.OK),
        )
    )

    assert report.ready is False


def test_otp_down_does_not_block_readiness() -> None:
    """OTP is a placeholder until A2 ships a graph bundle (N-08)."""
    report = ReadinessReport(
        components=(
            ComponentHealth("postgres", HealthStatus.OK),
            ComponentHealth("redis", HealthStatus.OK),
            ComponentHealth("otp", HealthStatus.DOWN, required=False),
        )
    )

    assert report.ready is True
