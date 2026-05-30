from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Protocol

from .models import BusSchedule


@dataclass
class RuleContext:
    operator_wait_so_far: Dict[str, int]
    operator_bus_count: Dict[str, int]
    scheduled_bus_count: int
    network_best_journey_min: int
    operator_station_counts: Dict[str, Dict[str, int]] | None = None


class SoftRule(Protocol):
    name: str

    def score(self, candidate: BusSchedule, context: RuleContext) -> float:
        ...


class IndividualWaitRule:
    name = "individual"

    def score(self, candidate: BusSchedule, context: RuleContext) -> float:
        # Penalize the worst single wait strongly, then total wait. This prevents sacrificing one bus.
        max_wait = max((event.wait_min for event in candidate.charge_events), default=0)
        return max_wait * 2.0 + candidate.total_wait_min


class OperatorSmoothnessRule:
    name = "operator"

    def score(self, candidate: BusSchedule, context: RuleContext) -> float:
        # Penalize pushing one operator's average wait above the current network average.
        op = candidate.operator
        projected_wait = context.operator_wait_so_far.get(op, 0) + candidate.total_wait_min
        projected_count = context.operator_bus_count.get(op, 0) + 1
        projected_operator_avg = projected_wait / projected_count

        total_wait = sum(context.operator_wait_so_far.values()) + candidate.total_wait_min
        total_count = context.scheduled_bus_count + 1
        network_avg = total_wait / total_count if total_count else 0
        station_counts = (context.operator_station_counts or {}).get(op, {})
        concentration = sum(station_counts.get(event.station, 0) for event in candidate.charge_events)
        return max(0.0, projected_operator_avg - network_avg) + 0.25 * projected_operator_avg + 40.0 * concentration


class OverallEfficiencyRule:
    name = "overall"

    def score(self, candidate: BusSchedule, context: RuleContext) -> float:
        # Penalize extra time beyond pure drive + charge time.
        return candidate.journey_min - context.network_best_journey_min


DEFAULT_RULES = [IndividualWaitRule(), OperatorSmoothnessRule(), OverallEfficiencyRule()]
