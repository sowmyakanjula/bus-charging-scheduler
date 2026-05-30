from scheduler.engine import ChargingScheduler
from scheduler.loader import list_scenario_files, load_scenario


def test_all_scenarios_valid():
    scheduler = ChargingScheduler()
    for path in list_scenario_files():
        scenario = load_scenario(path)
        result = scheduler.schedule(scenario)
        assert len(result.buses) == len(scenario.buses)
        for bus_schedule in result.buses:
            checkpoints = [bus_schedule.origin] + bus_schedule.plan + [bus_schedule.destination]
            assert len(bus_schedule.plan) >= 2
            for a, b in zip(checkpoints, checkpoints[1:]):
                leg = abs(scenario.network.positions[b] - scenario.network.positions[a])
                assert leg <= scenario.network.battery_range_km
            for event in bus_schedule.charge_events:
                assert event.end_min - event.start_min == scenario.network.charge_duration_min


def test_weight_override_changes_schedule_for_heavy_scenario():
    scenario = load_scenario([p for p in list_scenario_files() if p.name == "scenario_4.json"][0])
    scheduler = ChargingScheduler()
    low = scheduler.schedule(scenario, override_weights={"individual": 1, "operator": 0, "overall": 1})
    high = scheduler.schedule(scenario, override_weights={"individual": 1, "operator": 5, "overall": 1})
    low_plans = [(b.bus_id, tuple(b.plan), b.total_wait_min) for b in low.buses]
    high_plans = [(b.bus_id, tuple(b.plan), b.total_wait_min) for b in high.buses]
    assert low_plans != high_plans
