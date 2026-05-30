from __future__ import annotations

import itertools
from collections import defaultdict
from copy import deepcopy
from typing import Dict, Iterable, List, Tuple

from .models import Bus, BusSchedule, ChargeEvent, Network, Scenario, ScheduleResult
from .rules import DEFAULT_RULES, RuleContext, SoftRule
from .utils import parse_hhmm


class SchedulingError(ValueError):
    pass


class ChargingScheduler:
    """Greedy, rule-scored scheduler.

    The engine is intentionally small but extensible:
    - hard constraints live in plan enumeration / validation
    - soft optimization is a list of rule objects
    - scenario data controls network, chargers, buses and weights
    """

    def __init__(self, rules: Iterable[SoftRule] | None = None):
        self.rules = list(rules or DEFAULT_RULES)

    def schedule(self, scenario: Scenario, override_weights: Dict[str, float] | None = None) -> ScheduleResult:
        network = scenario.network
        weights = {**scenario.weights, **(override_weights or {})}
        station_available = self._initial_station_slots(network)
        station_events: Dict[str, List[ChargeEvent]] = defaultdict(list)
        bus_schedules: List[BusSchedule] = []
        operator_wait_so_far: Dict[str, int] = defaultdict(int)
        operator_bus_count: Dict[str, int] = defaultdict(int)
        operator_station_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        best_journey = network.travel_minutes(network.total_distance) + 2 * network.charge_duration_min

        for bus in sorted(scenario.buses, key=lambda b: (parse_hhmm(b.departure), b.id)):
            context = RuleContext(
                operator_wait_so_far=dict(operator_wait_so_far),
                operator_bus_count=dict(operator_bus_count),
                scheduled_bus_count=len(bus_schedules),
                network_best_journey_min=best_journey,
                operator_station_counts={op: dict(counts) for op, counts in operator_station_counts.items()},
            )
            candidates = []
            for plan in self.enumerate_feasible_plans(network, bus.origin, bus.destination):
                candidate = self._simulate_bus(bus, plan, network, station_available)
                candidates.append((self._score(candidate, context, weights), candidate))
            if not candidates:
                raise SchedulingError(f"No feasible charging plan for {bus.id}")

            _, chosen = min(candidates, key=lambda item: (item[0], item[1].arrival_min, len(item[1].plan), item[1].plan))
            self._commit_schedule(chosen, station_available, station_events)
            bus_schedules.append(chosen)
            operator_wait_so_far[chosen.operator] += chosen.total_wait_min
            operator_bus_count[chosen.operator] += 1
            for event in chosen.charge_events:
                operator_station_counts[chosen.operator][event.station] += 1

        return ScheduleResult(
            scenario=scenario,
            buses=bus_schedules,
            station_events={st: sorted(events, key=lambda e: (e.start_min, e.bus_id)) for st, events in station_events.items()},
            metrics=self._metrics(bus_schedules),
        )

    def enumerate_feasible_plans(self, network: Network, origin: str, destination: str) -> List[List[str]]:
        stations = self._stations_in_travel_order(network, origin, destination)
        feasible: List[List[str]] = []
        for r in range(1, len(stations) + 1):
            for combo in itertools.combinations(stations, r):
                if self._is_plan_feasible(network, origin, destination, list(combo)):
                    feasible.append(list(combo))
        # Prefer the minimum number of charging stops, but keep alternatives at +1 stop for congestion relief.
        min_len = min((len(p) for p in feasible), default=0)
        return [p for p in feasible if len(p) <= min_len + 1]

    def _stations_in_travel_order(self, network: Network, origin: str, destination: str) -> List[str]:
        stops = network.stops
        if origin not in stops or destination not in stops:
            raise SchedulingError(f"Unknown origin/destination: {origin}->{destination}")
        i, j = stops.index(origin), stops.index(destination)
        if i < j:
            ordered = stops[i + 1 : j]
        else:
            ordered = list(reversed(stops[j + 1 : i]))
        return [stop for stop in ordered if stop in network.station_chargers]

    def _distance_between(self, network: Network, start: str, end: str) -> float:
        return abs(network.positions[end] - network.positions[start])

    def _is_plan_feasible(self, network: Network, origin: str, destination: str, plan: List[str]) -> bool:
        checkpoints = [origin] + plan + [destination]
        return all(self._distance_between(network, a, b) <= network.battery_range_km for a, b in zip(checkpoints, checkpoints[1:]))

    def _initial_station_slots(self, network: Network) -> Dict[str, List[int]]:
        return {station: [0 for _ in range(chargers)] for station, chargers in network.station_chargers.items()}

    def _simulate_bus(
        self,
        bus: Bus,
        plan: List[str],
        network: Network,
        station_available: Dict[str, List[int]],
    ) -> BusSchedule:
        now = parse_hhmm(bus.departure)
        current = bus.origin
        events: List[ChargeEvent] = []
        slots = deepcopy(station_available)

        for station in plan:
            travel = network.travel_minutes(self._distance_between(network, current, station))
            arrival = now + travel
            slot_index, slot_ready = min(enumerate(slots[station]), key=lambda item: item[1])
            start = max(arrival, slot_ready)
            end = start + network.charge_duration_min
            slots[station][slot_index] = end
            events.append(
                ChargeEvent(
                    bus_id=bus.id,
                    operator=bus.operator,
                    station=station,
                    arrival_min=arrival,
                    start_min=start,
                    end_min=end,
                    wait_min=start - arrival,
                )
            )
            current = station
            now = end

        now += network.travel_minutes(self._distance_between(network, current, bus.destination))
        departure = parse_hhmm(bus.departure)
        total_wait = sum(event.wait_min for event in events)
        total_charge = len(events) * network.charge_duration_min
        journey = now - departure
        travel = journey - total_wait - total_charge
        return BusSchedule(
            bus_id=bus.id,
            operator=bus.operator,
            origin=bus.origin,
            destination=bus.destination,
            departure_min=departure,
            arrival_min=now,
            charge_events=events,
            plan=plan,
            total_wait_min=total_wait,
            total_charge_min=total_charge,
            travel_min=travel,
            journey_min=journey,
        )

    def _score(self, candidate: BusSchedule, context: RuleContext, weights: Dict[str, float]) -> float:
        total = 0.0
        for rule in self.rules:
            total += weights.get(rule.name, 0.0) * rule.score(candidate, context)
        return total

    def _commit_schedule(
        self,
        chosen: BusSchedule,
        station_available: Dict[str, List[int]],
        station_events: Dict[str, List[ChargeEvent]],
    ) -> None:
        for event in chosen.charge_events:
            slot_index, _ = min(enumerate(station_available[event.station]), key=lambda item: item[1])
            station_available[event.station][slot_index] = event.end_min
            station_events[event.station].append(event)

    def _metrics(self, schedules: List[BusSchedule]) -> Dict[str, object]:
        waits = [s.total_wait_min for s in schedules]
        by_operator: Dict[str, List[int]] = defaultdict(list)
        for schedule in schedules:
            by_operator[schedule.operator].append(schedule.total_wait_min)
        return {
            "buses": len(schedules),
            "total_wait_min": sum(waits),
            "avg_wait_min": round(sum(waits) / len(waits), 2) if waits else 0,
            "max_wait_min": max(waits) if waits else 0,
            "avg_journey_min": round(sum(s.journey_min for s in schedules) / len(schedules), 2) if schedules else 0,
            "operator_avg_wait_min": {op: round(sum(vals) / len(vals), 2) for op, vals in by_operator.items()},
        }
