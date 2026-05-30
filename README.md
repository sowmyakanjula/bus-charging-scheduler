# Bus Charging Scheduler

A Python + Streamlit take-home assignment solution for scheduling electric bus charging on a route with shared charging stations.

## What it does

- Loads scenario JSON files from `scenarios/`
- Generates a feasible charging plan for every bus
- Ensures every bus respects the 240 km range rule
- Ensures one bus uses a charger at a time at each station
- Uses configurable soft-rule weights for:
  - individual bus wait
  - operator smoothness
  - overall network efficiency
- Shows:
  - scenario input
  - per-bus timetable
  - per-station charger order
  - validation checks

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub.
2. Open Streamlit Community Cloud.
3. Create a new app from the GitHub repo.
4. Set the entry point to `app.py`.
5. Deploy.

## Project structure

```text
.
├── app.py
├── requirements.txt
├── scenarios/
│   ├── scenario_1.json
│   ├── scenario_2.json
│   ├── scenario_3.json
│   ├── scenario_4.json
│   └── scenario_5.json
├── scheduler/
│   ├── engine.py
│   ├── loader.py
│   ├── models.py
│   ├── rules.py
│   └── utils.py
├── test_scheduler.py
├── README.md
└── ARCHITECTURE.md
```

## How to change a weight

The obvious place is the scenario JSON file:

```json
"weights": {
  "individual": 1.0,
  "operator": 2.0,
  "overall": 1.0
}
```

The Streamlit sidebar also lets reviewers override weights live without changing code.

## How to add a new scenario

Create another JSON file in `scenarios/`, for example `scenario_6.json`, with the same shape:

```json
{
  "id": "scenario_6",
  "name": "Scenario 6 — New test",
  "description": "New departure schedule",
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
  },
  "weights": {"individual": 1.0, "operator": 1.0, "overall": 1.0},
  "buses": [
    {"id": "bus-BK-01", "operator": "kpn", "origin": "Bengaluru", "destination": "Kochi", "departure": "19:00"}
  ]
}
```

The app automatically discovers `scenario_*.json` files.

## How to add a new rule

Add a class in `scheduler/rules.py` with a `name` and `score()` method:

```python
class ElectricityCostRule:
    name = "electricity_cost"

    def score(self, candidate, context):
        return sum(peak_cost(event.start_min) for event in candidate.charge_events)
```

Then include it when creating the scheduler:

```python
scheduler = ChargingScheduler(rules=[
    IndividualWaitRule(),
    OperatorSmoothnessRule(),
    OverallEfficiencyRule(),
    ElectricityCostRule(),
])
```

And add the weight in the scenario file:

```json
"weights": {
  "individual": 1.0,
  "operator": 1.0,
  "overall": 1.0,
  "electricity_cost": 0.5
}
```

The engine does not need to be rewritten.

## Testing

```bash
pip install pytest
pytest
```

The tests validate all scenarios and confirm that weight tuning can change schedules.
