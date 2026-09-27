import re
from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from farm.auth import require
from farm.models import Pond, WaterVisit
from farm.services import number

MEASUREMENTS = {
    "oxygen": "Dissolved oxygen (mg/L)", "ph": "pH", "temperature": "Temperature (°C)",
    "secchi_cm": "Secchi depth (cm)", "tan_n": "TAN as NH3-N (mg/L)",
    "tan_nh3": "TAN as NH3 (mg/L)", "nh3": "Unionized NH3 (mg/L)",
    "tds_ppt": "TDS (ppt)", "alkalinity": "Alkalinity (mg/L)", "hardness": "Hardness (mg/L)",
}


def add_visit(engine, actor, pond_id, day, time, period, **values):
    user = require(engine, actor, "record")
    if day > date.today():
        raise ValueError("Visit date cannot be in the future.")
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
        raise ValueError("Time must be HH:MM in 24-hour format.")
    if period not in {"Morning", "Evening", "Other"}:
        raise ValueError("Select a valid observation period.")
    if not any(values.get(key) is not None for key in MEASUREMENTS):
        raise ValueError("Record at least one measurement.")
    for key in MEASUREMENTS:
        if values.get(key) is not None:
            number(values[key], MEASUREMENTS[key], 0, 14 if key == "ph" else 50 if key == "temperature" else None)
    if values.get("follow_up_on") and values["follow_up_on"] < day:
        raise ValueError("Follow-up date cannot precede the visit.")
    for key in ["equipment", "notes", "actions_requested"]:
        if len(values.get(key, "")) > (500 if key == "equipment" else 2000):
            raise ValueError(f"{key} exceeds the allowed length.")
    if values.get("actions_implemented", "Not recorded") not in {"Not recorded", "All", "Some", "None"}:
        raise ValueError("Unknown implementation status.")
    with Session(engine) as session, session.begin():
        if session.get(Pond, pond_id) is None:
            raise ValueError("Select an existing pond.")
        session.add(WaterVisit(pond_id=pond_id, day=day, time=time, period=period,
                               observer=user["name"] or str(user["id"]), **values))


def read_visits(engine, actor):
    require(engine, actor, "record")
    with engine.connect() as connection:
        return pd.read_sql(select(WaterVisit), connection)


def render_visits(engine, actor, ponds):
    import streamlit as st
    from sqlalchemy.exc import IntegrityError
    require(engine, actor, "record")
    st.title("Water visits")
    st.caption("Pond-level observations, including multiple readings per day. Ammonia measurement methods remain separate.")
    if ponds.empty:
        st.info("Ask a manager to create a pond before recording visits.")
        return
    names = ponds.set_index("id").name.to_dict()
    with st.form("water_visit", clear_on_submit=True):
        a, b, c = st.columns(3)
        with a:
            pond = st.selectbox("Pond", list(names), format_func=names.get)
            day = st.date_input("Visit date", max_value=date.today())
            measured_time = st.time_input("Local time")
            period = st.selectbox("Observation period", ["Morning", "Evening", "Other"])
            equipment = st.text_input("Equipment / method", max_chars=500)
        readings = {}
        for index, (key, label) in enumerate(MEASUREMENTS.items()):
            with b if index < 5 else c:
                readings[key] = st.number_input(label, min_value=0.0,
                    max_value=14.0 if key == "ph" else 50.0 if key == "temperature" else None,
                    value=None, key=f"visit_{key}")
        actions = st.text_area("Corrective actions requested", max_chars=2000)
        implemented = st.selectbox("Actions implemented", ["Not recorded", "All", "Some", "None"])
        follow_up = st.checkbox("This is a follow-up visit")
        follow_up_on = st.date_input("Next follow-up date (optional)", value=None)
        notes = st.text_area("Visit notes", max_chars=2000)
        if st.form_submit_button("Save water visit", type="primary"):
            try:
                add_visit(engine, actor, int(pond), day, measured_time.strftime("%H:%M"), period,
                          **readings, equipment=equipment, follow_up=follow_up, follow_up_on=follow_up_on,
                          actions_requested=actions, actions_implemented=implemented, notes=notes)
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
            except IntegrityError:
                st.error("A visit already exists for this pond, date and time.")
            else:
                st.success("Water visit saved.")
    visits = read_visits(engine, actor)
    st.dataframe(visits.sort_values(["day", "time"], ascending=False), hide_index=True, width="stretch")
