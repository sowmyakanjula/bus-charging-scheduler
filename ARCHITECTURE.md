# Architecture

## Summary

I used a data-driven greedy scheduling framework with rule-scored candidate plans.

For each bus, the engine enumerates all feasible charging plans that satisfy the hard range constraint, simulates each plan against the current charger availability, scores the candidate using configurable soft rules, and commits the best candidate. This keeps the engine simple, fast, and extensible while still producing defensible schedules for the given scenarios.

This is intentionally not a UI-heavy solution. The main value is in the scheduling model, the data structure, and the ability to add/change rules without rewriting the engine.

## Why this approach fits

The problem has two layers:

1. **Hard constraints** that must never be violated:
   - max 240 km between charges
   - charging takes exactly 25 minutes
   - one bus per charger slot at a time
   - buses move forward along the route only

2. **Soft optimization goals** that can change over time:
   - avoid one bus waiting too long
   - keep each operator's fleet running smoothly
   - reduce total network time

A rule-scored scheduler fits this because the hard constraints stay in the engine, while soft decisions are isolated as rule classes. New business preferences can be added by adding a rule and a weight, not by rewriting the scheduler.

## Data structure design

A scenario file is the source of truth. It includes:

- metadata: `id`, `name`, `description`
- network configuration:
  - speed
  - battery range
  - charge duration
  - route stops
  - segment distances
  - station charger counts
- weights:
  - individual
  - operator
  - overall
- buses:
  - id
  - operator
  - origin
  - destination
  - departure

Example:

```json
{
  "network": {
    "speed_kmph": 60,
    "battery_range_km": 240,
    "charge_duration_min": 25,
    "route": {
      "stops": ["Bengaluru", "A", "B", "C", "D", "Kochi"],
      "segments_km": [100, 120, 100, 120, 100]
    },
    "stations": {
      "A": {"chargers": 1},
      "B": {"chargers": 1},
      "C": {"chargers": 1},
      "D": {"chargers": 1}
    }
  }
}
```

This shape avoids hardcoding Bengaluru, Kochi, A, B, C, D, charger counts, distance, or weights into the scheduling engine.

## Scheduler flow

For every bus, ordered by scheduled departure:

1. Find stations between origin and destination in travel order.
2. Enumerate charging station combinations.
3. Keep only plans where every leg is within battery range.
4. Simulate each feasible plan against current station availability.
5. Score each candidate using weighted soft rules.
6. Commit the lowest-scoring candidate.
7. Update station availability and operator wait state.

## Hard rules

Hard rules are enforced before or during simulation:

- **Range rule:** candidate plans are rejected if any leg exceeds `battery_range_km`.
- **No backtracking:** station order is derived from route order based on origin and destination.
- **Charging duration:** every charge event uses `charge_duration_min`.
- **One bus per charger:** each station keeps a list of charger-slot availability times.

## Soft rules

Soft rules live in `scheduler/rules.py`.

Current rules:

1. `IndividualWaitRule`
   - Penalizes the worst single wait and total wait for a bus.

2. `OperatorSmoothnessRule`
   - Penalizes schedules that push one operator's average wait above the current network average.

3. `OverallEfficiencyRule`
   - Penalizes extra journey time beyond drive time plus required charge time.

The final score is:

```python
score = sum(weight[rule.name] * rule.score(candidate, context) for rule in rules)
```

## How to change a weight

In a scenario JSON:

```json
"weights": {
  "individual": 1.0,
  "operator": 2.0,
  "overall": 1.0
}
```

Or in code:

```python
result = scheduler.schedule(
    scenario,
    override_weights={"individual": 1.0, "operator": 5.0, "overall": 1.0},
)
```

The Streamlit sidebar exposes this for live review.

## How to add a new rule

Add a rule class:

```python
class DriverShiftRule:
    name = "driver_shift"

    def score(self, candidate, context):
        shift_limit = 8 * 60
        return max(0, candidate.journey_min - shift_limit)
```

Register it:

```python
scheduler = ChargingScheduler(rules=[
    IndividualWaitRule(),
    OperatorSmoothnessRule(),
    OverallEfficiencyRule(),
    DriverShiftRule(),
])
```

Add a scenario weight:

```json
"weights": {
  "individual": 1.0,
  "operator": 1.0,
  "overall": 1.0,
  "driver_shift": 3.0
}
```

No scheduler rewrite is required.

## Future changes anticipated

### 1. More stations

Handled by data. Add the station to `route.stops`, add its segment distance, and add it under `stations` if it has chargers. The engine computes positions dynamically.

### 2. Different segment distances

Handled by data. Change `segments_km`; all travel times and range checks update automatically.

### 3. More chargers at a station

Handled by data. Change:

```json
"B": {"chargers": 2}
```

The engine already models each charger as an independent availability slot.

### 4. More buses

Handled by data. Add bus objects to `buses`. The engine loops over the list.

### 5. New operators

Handled by data. Any string is accepted as an operator. Operator-level metrics and smoothness scoring are computed dynamically.

### 6. Different origins and destinations on the same route

Handled by data as long as both are stops in the route. The scheduler derives the station order between them.

### 7. Reverse direction travel

Handled by data. The engine reverses route order when origin appears after destination.

### 8. Different battery ranges

Currently scenario-level and handled by data via `battery_range_km`. If buses later have individual battery ranges, the bus schema can add `battery_range_km`; the range-checking method would read bus-level override first and scenario default second.

### 9. Different charging durations by station or charger

Currently scenario-level. The data structure can be extended to:

```json
"stations": {
  "B": {"chargers": 2, "charge_duration_min": 20}
}
```

The engine would read station-level duration with scenario fallback.

### 10. Time-of-day electricity pricing

Add a soft rule like `ElectricityCostRule` and add price windows to scenario data. This does not change hard scheduling logic.

### 11. Priority buses

Add a bus field:

```json
"priority": 2
```

Then add a `PriorityRule` that reduces penalty for high-priority buses or increases penalty when they wait.

### 12. Driver shift constraints

Add a hard validator or soft rule depending on product need. If strict, reject candidates that exceed shift length. If flexible, penalize them.

### 13. Multiple routes sharing stations

The current station model is name-based and shared. Multiple route definitions could refer to the same station IDs. The station availability map would still serialize access by station ID.

### 14. Maintenance windows / charger downtime

Add unavailable windows to station data:

```json
"B": {"chargers": 1, "closed_windows": [{"start": "22:00", "end": "23:00"}]}
```

Then add a station availability function that skips closed windows.

### 15. Minimum state-of-charge buffer

Instead of using full range, add a buffer:

```json
"min_range_buffer_km": 20
```

The range validator would compare each leg against `battery_range_km - buffer`.

## Assumptions made

- All buses start fully charged at their origin.
- Bengaluru and Kochi are not scheduling stations.
- All buses travel at 60 km/h.
- Charging always fills to full and always takes 25 minutes.
- Buses are scheduled in departure-time order.
- A bus does not intentionally wait before reaching a charger unless the charger is occupied.
- The scheduler may use more than two charges if that reduces contention.
- Scenario times are same-day HH:MM values; arrivals may roll past midnight and are displayed with `+1d`.

## Tradeoffs

The current greedy approach is easy to explain and extend, and it is sufficient for the take-home scale. For much larger fleets, the same data model and rule interface could be used with a stronger optimizer such as OR-Tools CP-SAT, local search, or rolling-horizon optimization. The important design choice is that rules and data are separated from the engine, so the optimization backend can be swapped without changing scenario files or UI structure.
