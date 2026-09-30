from datetime import date, timedelta
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from farm.analytics import batch_metrics, water_alerts
from farm.db import initialize, make_engine, settings
from farm.demo import seed_demo
from farm.services import add_batch, add_pond, read_data, save_log
from farm.auth import PAGES, authorize_write, pages_for, require
from farm.auth_ui import render_users, sign_in
from farm.fwi_ui import render_fwi
from farm.insights_ui import render_insights
from farm.water import render_visits

st.set_page_config(page_title="Pondwise | Farm operations", page_icon="🐟", layout="wide")
st.markdown("""<style>
.block-container {padding-top:2rem; max-width:1500px;}
[data-testid="stMetric"] {background:white; border:1px solid #dbe5e9; padding:18px; border-radius:12px;}
h1,h2,h3 {letter-spacing:-0.035em;}
</style>""", unsafe_allow_html=True)

import requests
try:
    ip = requests.get(
        "https://api.ipify.org", timeout=10
    ).text.strip()
    st.write("Server outbound IP:", ip)
except requests.RequestException:
    st.write("Unable to retrieve server outbound IP.")

@st.cache_resource
def database():
    mode, url = settings()
    engine = make_engine(url)
    return mode, engine


try:
    mode, engine = database()
    initialize(engine)
    actor = sign_in(engine)
    ponds, batches, logs = read_data(engine)
except (ValueError, SQLAlchemyError):
    st.error("Database unavailable. Check APP_MODE, DATABASE_URL, and database connectivity. See README.md for setup.")
    st.stop()


def commit(action, *args, **kwargs):
    try:
        authorize_write(engine, actor, action, *args, **kwargs)
    except (ValueError, PermissionError) as exc:
        st.error(str(exc))
    except SQLAlchemyError:
        st.error("Could not save. Check for a duplicate name or a concurrent change, then refresh and try again.")
    else:
        st.session_state["notice"] = "Saved successfully."
        st.rerun()


def csv_bytes(frame):
    # Prevent user-entered labels from becoming spreadsheet formulas on export.
    frame = frame.copy()
    for column in frame.select_dtypes(include="object"):
        frame[column] = frame[column].map(lambda value: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value)
    return frame.to_csv(index=False).encode("utf-8-sig")


def chart(fig):
    fig.update_layout(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=10, r=10, t=20, b=10), legend_title_text="")
    st.plotly_chart(fig, width="stretch")


with st.sidebar:
    st.title("🐟 Pondwise")
    st.caption("FARM MANAGEMENT & ANALYTICS")
    allowed_pages = pages_for(engine, actor)
    page = st.radio("Workspace", allowed_pages)
    st.divider()
    if mode == "demo":
        st.info("DEMO · Local SQLite storage")
        if "Ponds & stocking" in allowed_pages and ponds.empty and st.button("Load sample farm", width="stretch"):
            require(engine, actor, "manage")
            seed_demo(engine)
            st.rerun()
    else:
        st.success("PostgreSQL connected")
    st.caption("One daily record per batch. Weights in grams; feed and harvest in kilograms.")

try:
    require(engine, actor, PAGES[page])
except PermissionError as exc:
    st.error(str(exc))
    st.stop()

if "notice" in st.session_state:
    st.success(st.session_state.pop("notice"))

if page == "User access":
    render_users(engine, actor)
elif page == "FWI data":
    render_fwi(engine, actor)
elif page == "Advanced insights":
    render_insights(engine, actor, ponds, batches, logs)
elif page == "Water visits":
    render_visits(engine, actor, ponds)
elif page == "Ponds & stocking":
    st.title("Ponds & stocking")
    st.caption("Set up your production units and register each stocking cycle.")
    left, right = st.columns(2)
    with left:
        st.subheader("Create a pond")
        with st.form("pond"):
            name = st.text_input("Pond name", max_chars=100)
            area = st.number_input("Surface area (m²)", min_value=0.01, value=1000.0)
            depth = st.number_input("Average depth (m)", min_value=0.01, value=1.5)
            if st.form_submit_button("Add pond", type="primary"):
                commit(add_pond, name, area, depth)
    with right:
        st.subheader("Stock a batch")
        if ponds.empty:
            st.info("Create a pond first.")
        else:
            names = ponds.set_index("id").name.to_dict()
            with st.form("stock"):
                pond_id = st.selectbox("Pond", list(names), format_func=names.get)
                batch_name = st.text_input("Batch name", max_chars=100)
                species = st.text_input("Species", value="Tilapia", max_chars=100)
                stocked = st.date_input("Stocking date", max_value=date.today())
                count = st.number_input("Fish stocked", min_value=1, value=1000, step=1)
                weight = st.number_input("Initial average weight (g)", min_value=0.01, value=25.0)
                if st.form_submit_button("Register batch", type="primary"):
                    commit(add_batch, int(pond_id), batch_name, species, stocked, count, weight)
    st.subheader("Pond register")
    st.dataframe(ponds, hide_index=True, width="stretch")
    st.subheader("Stocking register")
    st.dataframe(batches, hide_index=True, width="stretch")

elif page == "Daily records":
    st.title("Daily records")
    st.caption("Record feed, fish movements, growth and water conditions in one place.")
    if batches.empty:
        st.info("Add a stocking batch under Ponds & stocking, or load the sample farm.")
    else:
        names = batches.set_index("id").name.to_dict()
        batch_id = st.selectbox("Batch", list(names), format_func=names.get)
        batch = batches[batches.id == batch_id].iloc[0]
        day = st.date_input("Record date", min_value=batch.stocked_on, max_value=date.today())
        existing = logs[(logs.batch_id == batch_id) & (logs.day == day)]
        old = existing.iloc[0].to_dict() if not existing.empty else {}
        if old:
            st.info("An existing record is loaded. Saving a correction replaces all values for this date.")
        def value(key, default=0):
            result = old.get(key, default)
            return default if pd.isna(result) else result
        with st.form(f"daily_{batch_id}_{day}"):
            a, b, c = st.columns(3)
            with a:
                st.subheader("Operations")
                feed = st.number_input("Feed (kg)", min_value=0.0, value=float(value("feed_kg")))
                deaths = st.number_input("Deaths (fish)", min_value=0, value=int(value("deaths")), step=1)
                harvested = st.number_input("Harvested fish", min_value=0, value=int(value("harvest_count")), step=1)
                harvest_kg = st.number_input("Harvest weight (kg)", min_value=0.0, value=float(value("harvest_kg")))
            with b:
                st.subheader("Growth & water")
                st.caption("Leave unmeasured fields blank. Blank is not zero.")
                weight = st.number_input("Sample average weight (g)", min_value=0.01, value=value("weight_g", None))
                oxygen = st.number_input("Dissolved oxygen (mg/L)", min_value=0.0, value=value("oxygen", None))
                ph = st.number_input("pH", min_value=0.0, max_value=14.0, value=value("ph", None))
                temperature = st.number_input("Temperature (°C)", min_value=0.0, max_value=50.0, value=value("temperature", None))
            with c:
                st.subheader("Field notes")
                notes = st.text_area("Observations", value=value("notes", ""), max_chars=1000, height=180)
                replace = st.checkbox("Replace the existing record for this date", disabled=not bool(old))
            if st.form_submit_button("Save daily record", type="primary"):
                commit(save_log, int(batch_id), day, feed_kg=feed, deaths=deaths,
                       harvest_count=harvested, harvest_kg=harvest_kg, weight_g=weight,
                       oxygen=oxygen, ph=ph, temperature=temperature, notes=notes, replace=replace)
        st.subheader("Batch history")
        st.dataframe(logs[logs.batch_id == batch_id].sort_values("day", ascending=False), hide_index=True, width="stretch")

else:
    st.title("Farm overview" if page == "Overview" else "Reports & exports")
    st.caption("A clear view of production, growth and daily farm conditions.")
    if batches.empty:
        st.info("Your farm starts here. Load the sample farm from the sidebar or create your first pond and batch.")
        st.stop()
    a, b, c = st.columns([2, 1, 1])
    pond_names = ponds.set_index("id").name.to_dict()
    with a:
        selected = st.multiselect("Ponds", list(pond_names), default=list(pond_names), format_func=pond_names.get)
    with c:
        end = st.date_input("As of", value=date.today(), max_value=date.today())
    with b:
        start = st.date_input("Trend start", value=min(end, date.today() - timedelta(days=30)), max_value=end)
    selected_batches = batches[batches.pond_id.isin(selected)]
    scoped = logs[logs.batch_id.isin(selected_batches.id) & (logs.day <= end)]
    window = scoped[scoped.day >= start]
    metrics = batch_metrics(selected_batches, scoped, end)
    if metrics.empty:
        st.info("No stocked batches match these ponds and the selected date.")
        st.stop()
    if page == "Reports":
        st.subheader("Batch performance")
        st.caption("Cumulative values through the As of date. Daily records use the trend date range.")
        st.dataframe(metrics, hide_index=True, width="stretch")
        st.download_button("Download batch performance", csv_bytes(metrics), f"batch-performance-{end}.csv", "text/csv")
        st.subheader("Daily records")
        export = window.merge(selected_batches[["id", "name", "species"]], left_on="batch_id", right_on="id", suffixes=("", "_batch"))
        st.dataframe(export, hide_index=True, width="stretch")
        st.download_button("Download daily records", csv_bytes(export), f"daily-records-{start}-{end}.csv", "text/csv")
    else:
        st.caption("KPIs are cumulative through the As of date; trend charts use the selected date range.")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Estimated standing biomass", f"{metrics.biomass_kg.sum():,.0f} kg")
        k2.metric("Fish remaining", f"{metrics.fish_remaining.sum():,.0f}")
        k3.metric("Feed used", f"{metrics.feed_kg.sum():,.1f} kg")
        k4.metric("Harvested", f"{metrics.harvest_kg.sum():,.1f} kg")
        st.caption("Biomass uses each batch’s latest sample weight and current fish count. It is an estimate.")
        left, right = st.columns([2, 1])
        names = selected_batches.set_index("id").name.to_dict()
        plotted = window.copy()
        plotted["batch"] = plotted.batch_id.map(names)
        with left:
            st.subheader("Feed over time")
            if plotted.empty:
                st.info("No daily records in this period.")
            else:
                chart(px.bar(plotted, x="day", y="feed_kg", color="batch", color_discrete_sequence=px.colors.qualitative.Safe,
                             labels={"day": "Date", "feed_kg": "Feed (kg)"}))
        with right:
            st.subheader("Attention needed")
            with st.expander("Alert thresholds"):
                st.caption("Illustrative defaults; set limits appropriate for your species and farm. Applies to this session.")
                oxygen_min = st.number_input("Minimum oxygen (mg/L)", min_value=0.0, value=4.0)
                ph_min = st.number_input("Minimum pH", min_value=0.0, max_value=14.0, value=6.5)
                ph_max = st.number_input("Maximum pH", min_value=ph_min, max_value=14.0, value=max(8.5, ph_min))
            active = metrics[metrics.fish_remaining > 0]
            active_logs = scoped[scoped.batch_id.isin(active.batch_id)]
            alerts = water_alerts(active_logs, names, end, oxygen_min, ph_min, ph_max)
            for alert in alerts:
                st.warning(alert)
            stale = active[active.sample_age_days > 7]
            for row in stale.itertuples():
                st.warning(f"{row.batch}: growth sample is {row.sample_age_days} days old.")
            for batch_key in active.batch_id:
                readings = active_logs[(active_logs.batch_id == batch_key) & active_logs.oxygen.notna() & active_logs.ph.notna()]
                if readings.empty or (end - readings.day.max()).days > 1:
                    st.info(f"{names[batch_key]}: no complete oxygen/pH check within the last day.")
            if not alerts and stale.empty:
                st.caption("No threshold breaches in available readings. Check dates and missing measurements.")
        x, y = st.columns(2)
        with x:
            st.subheader("Growth samples")
            growth = plotted[plotted.weight_g.notna()]
            if growth.empty:
                st.info("No growth samples in this period.")
            else:
                chart(px.line(growth.sort_values("day"), x="day", y="weight_g", color="batch", markers=True,
                              labels={"day": "Date", "weight_g": "Average weight (g)"}))
        with y:
            st.subheader("Dissolved oxygen")
            water = plotted[plotted.oxygen.notna()]
            if water.empty:
                st.info("No oxygen readings in this period.")
            else:
                fig = px.line(water.sort_values("day"), x="day", y="oxygen", color="batch", markers=True,
                              labels={"day": "Date", "oxygen": "Oxygen (mg/L)"})
                fig.add_hline(y=oxygen_min, line_dash="dot", line_color="#c76630")
                chart(fig)
        st.subheader("Batch performance")
        st.dataframe(metrics.drop(columns=["batch_id", "pond_id"]), hide_index=True, width="stretch")
    with st.expander("How the metrics are calculated"):
        st.markdown("""- **Fish remaining:** stocked fish − cumulative deaths − harvested fish.
- **Survival:** (stocked fish − deaths) ÷ stocked fish. Harvests are not mortality.
- **Biomass:** remaining fish × latest average weight ÷ 1,000.
- **FCR:** feed through the latest sample date ÷ (standing biomass at that date + harvested biomass − initial stocked biomass). Blank when growth is nonpositive or no sample exists. Mortality biomass is not recovered in this economic FCR estimate.
- **Sample age:** days since the latest growth sample, or stocking when no sample exists.
- Missing daily records are unrecorded activity, not confirmation of zero feed or mortality.
- Water alerts use the latest available reading per parameter and show its date.""")
