"""The price data files themselves (F-12, F-13, F-14, N-02, N-09)."""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest

from app.pricing import DataStatus, PricingData, PricingDataError, load_pricing_data
from app.pricing.models import DestinationArea, ParkingLot
from app.regions import RegionConfig, load_region_config
from app.regions.loader import REPO_ROOT

DEMO_DAY = date(2026, 10, 15)


@pytest.fixture(scope="module")
def nyc() -> RegionConfig:
    return load_region_config("data/regions/nyc-metro.yaml")


@pytest.fixture(scope="module")
def pricing(nyc: RegionConfig) -> PricingData:
    return load_pricing_data(nyc)


@pytest.fixture(scope="module")
def station_ids() -> set[str]:
    path = REPO_ROOT / "data" / "regions" / "nyc-metro-stations.csv"
    with path.open(encoding="utf-8") as handle:
        return {row["canonical_station_id"] for row in csv.DictReader(handle)}


def test_every_kind_of_price_file_is_present(pricing: PricingData) -> None:
    assert pricing.rail_fares and pricing.flat_fares
    assert pricing.crossing_tolls and pricing.zone_tolls
    assert pricing.parking_lots and pricing.destination_parking
    assert pricing.vehicle_defaults and pricing.ticket_tolls and pricing.barrier_tolls


def test_all_price_files_are_in_effect_on_the_demo_day(pricing: PricingData) -> None:
    files = [
        *pricing.rail_fares,
        *pricing.flat_fares,
        *pricing.crossing_tolls,
        *pricing.zone_tolls,
        *pricing.parking_lots,
        *pricing.destination_parking,
        *pricing.vehicle_defaults,
    ]
    for item in files:
        assert item.in_effect(DEMO_DAY), f"{item.kind} not in effect on {DEMO_DAY}"


def test_fares_and_lots_point_at_real_canonical_stations(
    pricing: PricingData, station_ids: set[str]
) -> None:
    for table in pricing.rail_fares:
        for fare in table.fares:
            assert fare.from_station in station_ids
            assert fare.to_station in station_ids
    for lots in pricing.parking_lots:
        for lot in lots.lots:
            assert lot.station in station_ids


def test_demo_corridor_has_a_fare_and_a_lot_for_every_station(pricing: PricingData) -> None:
    fare_origins = {f.from_station for t in pricing.rail_fares for f in t.fares}
    lot_stations = {lot.station for group in pricing.parking_lots for lot in group.lots}
    assert fare_origins == lot_stations
    assert len(lot_stations) == 4


def test_unknown_prices_carry_no_number() -> None:
    """N-02: unknown stays unknown. A guessed price under an 'unknown' label is rejected."""
    with pytest.raises(ValueError, match="exactly when status is unknown"):
        DestinationArea.model_validate(
            {
                "area_id": "x",
                "name": "x",
                "status": "unknown",
                "daily_usd": 40.0,
                "source": {"retrieved": "2026-10-14"},
            }
        )


def test_a_published_price_without_a_source_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="source url"):
        ParkingLot.model_validate(
            {
                "lot_id": "x",
                "station": "s",
                "name": "x",
                "operator": "x",
                "address": "x",
                "status": "scheduled",
                "rate_tiers": [{"max_hours": 24, "usd": 10}],
                "source": {"retrieved": "2026-10-14"},
            }
        )


def test_lot_rate_tiers_pick_the_first_tier_that_covers_the_stay(pricing: PricingData) -> None:
    lots = {lot.lot_id: lot for group in pricing.parking_lots for lot in group.lots}
    hamilton = lots["hamilton-deck"]

    assert hamilton.daily_cost(12) == hamilton.rate_tiers[0].usd
    assert hamilton.daily_cost(18) == hamilton.rate_tiers[1].usd
    assert hamilton.daily_cost(30) is None


def test_unknown_lot_price_reports_none_not_zero(pricing: PricingData) -> None:
    unknown = [
        lot
        for group in pricing.parking_lots
        for lot in group.lots
        if lot.status is DataStatus.UNKNOWN
    ]
    for lot in unknown:
        assert lot.daily_cost(10) is None


def test_a_malformed_file_fails_loudly(nyc: RegionConfig, tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text("kind: flat_fare\nagency: x\n", encoding="utf-8")
    broken = nyc.model_copy(
        update={"data_files": nyc.data_files.model_copy(update={"fares_dir": str(tmp_path)})}
    )
    with pytest.raises(PricingDataError):
        load_pricing_data(broken)


def test_monthly_passes_come_from_the_same_sourced_fare_chart(pricing: PricingData) -> None:
    for table in pricing.rail_fares:
        for fare in table.fares:
            assert fare.monthly_pass is not None and table.source.url
            assert fare.monthly_pass > fare.adult_one_way


def test_working_days_are_sourced_and_marked_estimated() -> None:
    from app.trips.corridor import load_corridor

    corridor = load_corridor(REPO_ROOT / "data" / "regions" / "nyc-metro-demo-corridor.yaml")

    assert corridor.commute.status is DataStatus.ESTIMATED  # a calendar count, not a timetable
    assert corridor.commute.source.url
