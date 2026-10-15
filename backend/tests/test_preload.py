"""Startup preload of the trip service (demo item 1): skipped in tests and without GTFS."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import ModuleType

import pytest

from app.config import Settings
from app.trips import factory


def _main() -> ModuleType:
    # Imported lazily: app.main builds a module-level app from get_settings(), which must not
    # be cached before conftest sets ENVIRONMENT=test.
    from app import main

    return main


def _run_lifespan(settings: Settings) -> None:
    main_module = _main()
    app = main_module.create_app(settings)

    async def _go() -> None:
        async with main_module.lifespan(app):
            pass

    asyncio.run(_go())


def test_preload_skipped_when_environment_is_test(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(_main(), "preload_in_background", lambda: calls.append("x"))

    _run_lifespan(Settings(environment="test"))  # type: ignore[arg-type]

    assert calls == []


def test_preload_starts_outside_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(_main(), "preload_in_background", lambda: calls.append("x"))

    _run_lifespan(Settings(environment="development"))  # type: ignore[arg-type]

    assert calls == ["x"]


def test_preload_skipped_when_gtfs_archive_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(factory, "transit_archive_path", lambda: tmp_path / "missing.zip")
    built: list[str] = []
    monkeypatch.setattr(factory, "get_trip_service", lambda: built.append("x"))

    assert factory.preload_in_background() is None
    assert built == []


def test_preload_runs_the_build_on_a_background_thread(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    archive = tmp_path / "feed.zip"
    archive.write_bytes(b"")
    monkeypatch.setattr(factory, "transit_archive_path", lambda: archive)
    built: list[str] = []
    monkeypatch.setattr(factory, "get_trip_service", lambda: built.append("x"))

    thread = factory.preload_in_background()

    assert thread is not None and thread.daemon
    thread.join(timeout=5)
    assert built == ["x"]
