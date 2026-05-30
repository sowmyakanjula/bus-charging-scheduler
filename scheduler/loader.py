from __future__ import annotations

import json
from pathlib import Path
from typing import List

from .models import Bus, Network, Scenario


def scenario_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "scenarios"


def list_scenario_files() -> List[Path]:
    return sorted(scenario_dir().glob("scenario_*.json"))


def load_scenario(path: Path) -> Scenario:
    raw = json.loads(path.read_text(encoding="utf-8"))
    net = raw["network"]
    network = Network(
        speed_kmph=float(net["speed_kmph"]),
        battery_range_km=float(net["battery_range_km"]),
        charge_duration_min=int(net["charge_duration_min"]),
        stops=list(net["route"]["stops"]),
        segments_km=list(map(float, net["route"]["segments_km"])),
        station_chargers={k: int(v.get("chargers", 1)) for k, v in net["stations"].items()},
    )
    buses = [Bus(**item) for item in raw["buses"]]
    return Scenario(
        id=raw["id"],
        name=raw["name"],
        description=raw.get("description", ""),
        network=network,
        weights={k: float(v) for k, v in raw.get("weights", {}).items()},
        buses=buses,
        raw=raw,
    )
