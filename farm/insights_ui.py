from datetime import date, timedelta
import hashlib
import json

import pandas as pd
import plotly.express as px
import streamlit as st

from farm.auth import require
from farm.insights import KPI_METRICS, evidence_packet, kpi_trend, trend_statistics, trend_table
from farm.llm import ask, configuration
from farm.water import MEASUREMENTS, read_visits


def render_insights(engine, actor, ponds, batches, logs):
    require(engine, actor, "analyze")
    st.title("Advanced insights")
    st.caption("Explore observed trends and ask questions using the selected data as evidence.")
    choices = ["Farm daily records", "Pond water visits"]
    source = st.selectbox("Data source", choices)
    source_details = source
    if source == "Farm daily records":
        frame = logs[["batch_id", "day", "feed_kg", "deaths", "harvest_kg", "weight_g", "oxygen", "ph", "temperature"]].copy()
        batch_ponds = batches.set_index("id").pond_id.to_dict()
        frame["pond"] = frame.batch_id.map(batch_ponds).map(ponds.set_index("id").name.to_dict())
        frame["period"] = "Daily"
        metrics = {"feed_kg": "Feed (kg)", "deaths": "Deaths (fish)", "harvest_kg": "Harvest (kg)",
                   "weight_g": "Sample weight (g)", **{k: MEASUREMENTS[k] for k in ["oxygen", "ph", "temperature"]}}
        metrics.update(KPI_METRICS)
    elif source == "Pond water visits":
        visits = read_visits(engine, actor)
        frame = visits[["day", "period", *MEASUREMENTS]].copy()
        frame["pond"] = visits.pond_id.map(ponds.set_index("id").name.to_dict())
        metrics = MEASUREMENTS
    if frame.empty:
        st.info("No observations available for this source. Record farm activity or pond water visits first.")
        return
    options = sorted(frame.pond.dropna().unique())
    selected = st.multiselect("Ponds in analysis", options, default=options)
    left, middle, right = st.columns(3)
    min_day, max_day = min(frame.day), max(frame.day)
    with left:
        start = st.date_input("From", value=max(min_day, max_day - timedelta(days=90)), key=f"insight_start_{source}")
    with middle:
        end = st.date_input("Through", value=max_day, key=f"insight_end_{source}")
    with right:
        frequency = st.selectbox("Trend interval", ["Daily", "Weekly", "Monthly"], index=1)
    if start > end:
        st.error("From date must not be after Through date.")
        return
    frame = frame[frame.pond.isin(selected) & (frame.day >= start) & (frame.day <= end)].copy()
    if frame.empty:
        st.info("No observations match the selected ponds and dates.")
        return
    metric = st.selectbox("Metric", list(metrics), format_func=metrics.get)
    aggregation = "sum" if metric in {"feed_kg", "deaths", "harvest_kg"} else "mean"
    if source == "Farm daily records" and metric in KPI_METRICS:
        selected_batches = batches[batches.pond_id.isin(ponds[ponds.name.isin(selected)].id)]
        trend = kpi_trend(selected_batches, logs, start, end, metric, frequency)
        aggregation = "period-end snapshot by batch"
        st.subheader(f"{metrics[metric]} · {frequency.lower()} snapshots")
        st.caption("Cumulative through each period end, capped at the selected end date. Biomass uses the last known sample; FCR is aligned to that sample. Review sample dates in the table.")
    else:
        trend = trend_table(frame, metric, frequency, aggregation)
        st.subheader(f"{metrics[metric]} · {frequency.lower()} {'total' if aggregation == 'sum' else 'mean'}")
        st.caption("Missing periods stay blank. Means are weighted by observations; changes in which ponds were sampled can affect the trend.")
    if trend.value.notna().any():
        fig = px.line(trend, x="period_start", y="value", color="series", markers=True,
                      labels={"period_start": "Period beginning", "value": metrics[metric], "series": "Observation period"})
        fig.update_traces(connectgaps=False)
        st.plotly_chart(fig, width="stretch")
        summary = pd.DataFrame(trend_statistics(trend))
        st.dataframe(summary, hide_index=True, width="stretch")
        st.caption("Change compares the last two observed periods. Slope is a descriptive linear fit per day across at least three observed periods; it is not a forecast.")
    else:
        st.info("This metric was not measured in the selected observations.")
    with st.expander("Trend values and observation counts"):
        st.dataframe(trend, hide_index=True, width="stretch")
    scope = {"source": source_details, "from": str(start), "through": str(end),
             "pond_count": len(selected), "ponds_first_30": selected[:30],
             "interval": frequency, "aggregation": aggregation, "metric": metrics[metric]}
    kwargs = {}
    if source == "Farm daily records":
        pond_ids = ponds[ponds.name.isin(selected)].id
        scoped_batches = batches[batches.pond_id.isin(pond_ids)]
        kwargs = {"batches": scoped_batches, "logs": logs[logs.batch_id.isin(scoped_batches.id)], "as_of": end}
    evidence = evidence_packet(frame, metric, trend, scope, **kwargs)
    st.divider()
    st.subheader("Ask your farm data")
    st.caption("Try: Which measured conditions are worsening? What should we check next? Which data gaps limit the analysis?")
    with st.expander("Evidence supplied to the model"):
        st.json(evidence)
    try:
        config = configuration()
    except ValueError as exc:
        st.error(str(exc))
        return
    fingerprint = hashlib.sha256(json.dumps({"evidence": evidence, "user": actor.user_id,
                                             "config": config}, sort_keys=True).encode()).hexdigest()
    if st.session_state.get("chat_scope") != fingerprint:
        st.session_state["chat_scope"] = fingerprint
        st.session_state["chat_messages"] = []
    if st.button("Clear conversation"):
        st.session_state["chat_messages"] = []
    if not config["model"]:
        st.info("Chat is ready to connect. Set LLM_MODEL and start your Ollama server, or configure a hosted compatible endpoint. See docs/INSIGHTS.md.")
    else:
        st.caption(f"Model: {config['model']} · Endpoint: {config['endpoint']}")
        st.caption("Your question and the displayed evidence are sent to this endpoint. Staff identities and free-text field notes are excluded. Answers require review against the evidence.")
    for message in st.session_state["chat_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    question = st.chat_input("Ask a question about this analysis", disabled=not bool(config["model"]), max_chars=4000)
    if question:
        with st.chat_message("user"):
            st.markdown(question)
        try:
            with st.spinner("Analyzing the selected farm evidence…"):
                answer = ask(engine, actor, question, evidence, st.session_state["chat_messages"], config)
            require(engine, actor, "analyze")
        except (ValueError, PermissionError) as exc:
            st.error(str(exc))
        else:
            st.session_state["chat_messages"].extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
            st.session_state["chat_messages"] = st.session_state["chat_messages"][-12:]
            with st.chat_message("assistant"):
                st.markdown(answer)
