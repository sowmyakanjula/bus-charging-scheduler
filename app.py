from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from scheduler.engine import ChargingScheduler
from scheduler.loader import list_scenario_files, load_scenario
from scheduler.utils import fmt_duration, fmt_time


st.set_page_config(page_title="Bus Charging Scheduler", layout="wide")


def bus_input_df(scenario):
    rows = []
    for bus in scenario.buses:
        direction = f"{bus.origin}→{bus.destination}"
        rows.append({"Bus ID": bus.id, "Operator": bus.operator, "Direction": direction, "Departure": bus.departure})
    return pd.DataFrame(rows)


def bus_output_df(result):
    rows = []
    for schedule in sorted(result.buses, key=lambda s: (s.departure_min, s.bus_id)):
        charge_summary = []
        for e in schedule.charge_events:
            charge_summary.append(
                f"{e.station}: arrive {fmt_time(e.arrival_min)}, start {fmt_time(e.start_min)}, "
                f"end {fmt_time(e.end_min)}, wait {e.wait_min}m"
            )
        rows.append(
            {
                "Bus ID": schedule.bus_id,
                "Operator": schedule.operator,
                "Direction": f"{schedule.origin}→{schedule.destination}",
                "Departure": fmt_time(schedule.departure_min),
                "Charging Plan": " → ".join(schedule.plan),
                "Charging Timeline": " | ".join(charge_summary),
                "Total Wait": fmt_duration(schedule.total_wait_min),
                "Arrival": fmt_time(schedule.arrival_min),
                "Journey Time": fmt_duration(schedule.journey_min),
            }
        )
    return pd.DataFrame(rows)


def station_df(events):
    return pd.DataFrame(
        [
            {
                "Order": i,
                "Bus ID": event.bus_id,
                "Operator": event.operator,
                "Arrives": fmt_time(event.arrival_min),
                "Starts Charging": fmt_time(event.start_min),
                "Ends Charging": fmt_time(event.end_min),
                "Wait": fmt_duration(event.wait_min),
            }
            for i, event in enumerate(events, 1)
        ]
    )


st.title("Bus Charging Scheduler")
st.caption("Python + Streamlit take-home solution. Pick a scenario to see the input, bus timelines, and station queues.")

files = list_scenario_files()
scenarios = {load_scenario(path).name: path for path in files}
selected_name = st.selectbox("Scenario", list(scenarios.keys()))
scenario = load_scenario(scenarios[selected_name])

with st.sidebar:
    st.header("Weights")
    st.write("Defaults come from the scenario file. Adjust them here to test tunability without changing code.")
    individual = st.number_input("individual", min_value=0.0, value=float(scenario.weights.get("individual", 1.0)), step=0.25)
    operator = st.number_input("operator", min_value=0.0, value=float(scenario.weights.get("operator", 1.0)), step=0.25)
    overall = st.number_input("overall", min_value=0.0, value=float(scenario.weights.get("overall", 1.0)), step=0.25)
    override_weights = {"individual": individual, "operator": operator, "overall": overall}

scheduler = ChargingScheduler()
result = scheduler.schedule(scenario, override_weights=override_weights)

st.subheader(scenario.name)
st.write(scenario.description)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Buses", result.metrics["buses"])
c2.metric("Total wait", fmt_duration(result.metrics["total_wait_min"]))
c3.metric("Avg wait", fmt_duration(round(result.metrics["avg_wait_min"])))
c4.metric("Max wait", fmt_duration(result.metrics["max_wait_min"]))

st.divider()

st.header("Scenario input")
with st.expander("Readable bus table", expanded=True):
    st.dataframe(bus_input_df(scenario), use_container_width=True, hide_index=True)

with st.expander("Raw scenario data"):
    st.json(scenario.raw)

st.header("Per-bus timetable")
st.dataframe(bus_output_df(result), use_container_width=True, hide_index=True)

st.header("Per-station charging order")
tabs = st.tabs(list(scenario.network.station_chargers.keys()))
for tab, station in zip(tabs, scenario.network.station_chargers.keys()):
    with tab:
        events = result.station_events.get(station, [])
        if events:
            st.dataframe(station_df(events), use_container_width=True, hide_index=True)
        else:
            st.info("No buses charged here in this scenario.")

st.header("Validation checks")
validation_rows = []
for bus_schedule in result.buses:
    checkpoints = [bus_schedule.origin] + bus_schedule.plan + [bus_schedule.destination]
    max_leg = 0
    valid = True
    for a, b in zip(checkpoints, checkpoints[1:]):
        leg = abs(scenario.network.positions[b] - scenario.network.positions[a])
        max_leg = max(max_leg, leg)
        if leg > scenario.network.battery_range_km:
            valid = False
    validation_rows.append(
        {
            "Bus ID": bus_schedule.bus_id,
            "Plan": " → ".join(bus_schedule.plan),
            "Max distance between charges": f"{max_leg:.0f} km",
            "Range valid": valid,
            "Charges": len(bus_schedule.plan),
        }
    )
st.dataframe(pd.DataFrame(validation_rows), use_container_width=True, hide_index=True)
