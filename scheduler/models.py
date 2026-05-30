from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class Bus:
    id: str
    operator: str
    origin: str
    destination: str
    departure: str


@dataclass(frozen=True)
class Network:
    speed_kmph: float
    battery_range_km: float
    charge_duration_min: int
    stops: List[str]
    segments_km: List[float]
    station_chargers: Dict[str, int]

    @property
    def positions(self) -> Dict[str, float]:
        pos = {self.stops[0]: 0.0}
        total = 0.0
        for start, dist in zip(self.stops[1:], self.segments_km):
            total += dist
            pos[start] = total
        return pos

    @property
    def total_distance(self) -> float:
        return sum(self.segments_km)

    def travel_minutes(self, distance_km: float) -> int:
        return round((distance_km / self.speed_kmph) * 60)


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    description: str
    network: Network
    weights: Dict[str, float]
    buses: List[Bus]
    raw: Dict[str, Any] = field(repr=False)


@dataclass
class ChargeEvent:
    bus_id: str
    operator: str
    station: str
    arrival_min: int
    start_min: int
    end_min: int
    wait_min: int


@dataclass
class BusSchedule:
    bus_id: str
    operator: str
    origin: str
    destination: str
    departure_min: int
    arrival_min: int
    charge_events: List[ChargeEvent]
    plan: List[str]
    total_wait_min: int
    total_charge_min: int
    travel_min: int
    journey_min: int


@dataclass
class ScheduleResult:
    scenario: Scenario
    buses: List[BusSchedule]
    station_events: Dict[str, List[ChargeEvent]]
    metrics: Dict[str, Any]
