"""Load every price data file for a region, dispatching on each file's `kind`."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import Field, TypeAdapter, ValidationError

from app.pricing.models import (
    BarrierToll,
    CrossingToll,
    DestinationParking,
    FlatFare,
    ParkingLots,
    RailFares,
    TicketToll,
    VehicleDefaults,
    ZoneToll,
)
from app.regions.loader import resolve_region_path
from app.regions.schema import RegionConfig

PriceFile = Annotated[
    RailFares
    | FlatFare
    | CrossingToll
    | TicketToll
    | BarrierToll
    | ZoneToll
    | ParkingLots
    | DestinationParking
    | VehicleDefaults,
    Field(discriminator="kind"),
]
_ADAPTER: TypeAdapter[PriceFile] = TypeAdapter(PriceFile)


class PricingDataError(RuntimeError):
    """A price file is malformed. Never partially applied."""


@dataclass(frozen=True)
class PricingData:
    rail_fares: list[RailFares] = field(default_factory=list)
    flat_fares: list[FlatFare] = field(default_factory=list)
    crossing_tolls: list[CrossingToll] = field(default_factory=list)
    zone_tolls: list[ZoneToll] = field(default_factory=list)
    ticket_tolls: list[TicketToll] = field(default_factory=list)
    barrier_tolls: list[BarrierToll] = field(default_factory=list)
    parking_lots: list[ParkingLots] = field(default_factory=list)
    destination_parking: list[DestinationParking] = field(default_factory=list)
    vehicle_defaults: list[VehicleDefaults] = field(default_factory=list)


def _parse(path: Path) -> PriceFile:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return _ADAPTER.validate_python(raw)
    except (yaml.YAMLError, ValidationError) as exc:
        raise PricingDataError(f"{path}: {exc}") from exc


def load_pricing_data(region: RegionConfig) -> PricingData:
    files = region.data_files
    data = PricingData()
    for directory in (files.fares_dir, files.tolls_dir, files.parking_dir, files.vehicle_dir):
        for path in sorted(resolve_region_path(directory).glob("*.yaml")):
            match _parse(path):
                case RailFares() as item:
                    data.rail_fares.append(item)
                case FlatFare() as item:
                    data.flat_fares.append(item)
                case CrossingToll() as item:
                    data.crossing_tolls.append(item)
                case ZoneToll() as item:
                    data.zone_tolls.append(item)
                case TicketToll() as item:
                    data.ticket_tolls.append(item)
                case BarrierToll() as item:
                    data.barrier_tolls.append(item)
                case ParkingLots() as item:
                    data.parking_lots.append(item)
                case DestinationParking() as item:
                    data.destination_parking.append(item)
                case VehicleDefaults() as item:
                    data.vehicle_defaults.append(item)
    return data
