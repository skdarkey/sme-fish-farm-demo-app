"""Deterministic trend calculations and bounded, read-only LLM evidence."""
import json

import numpy as np
import pandas as pd

from farm.analytics import batch_metrics

KPI_METRICS = {"biomass_kg": "Estimated biomass (kg)", "fish_remaining": "Fish remaining",
               "survival_pct": "Survival (%)", "fcr": "Economic FCR"}


def kpi_trend(batches, logs, start, end, metric, frequency):
    code = {"Daily": "D", "Weekly": "W-SUN", "Monthly": "M"}[frequency]
    periods = pd.period_range(start, end, freq=code)
    rows = []
    for period in periods:
        as_of = min(period.end_time.date(), end)
        snapshot = batch_metrics(batches, logs, as_of)
        for row in snapshot.to_dict("records"):
            rows.append({"period_start": period.start_time.date(), "series": row["batch"],
                         "value": row[metric], "observations": None,
                         "snapshot_as_of": as_of, "sample_day": row["sample_day"]})
    return pd.DataFrame(rows, columns=["period_start", "series", "value", "observations", "snapshot_as_of", "sample_day"])


def trend_table(frame, metric, frequency="Weekly", aggregation="mean"):
    if frame.empty:
        return pd.DataFrame(columns=["period_start", "series", "value", "observations"])
    data = frame.copy()
    data["day"] = pd.to_datetime(data.day)
    data[metric] = pd.to_numeric(data[metric], errors="coerce").replace([np.inf, -np.inf], np.nan)
    code = {"Daily": "D", "Weekly": "W-SUN", "Monthly": "M"}[frequency]
    data["bucket"] = data.day.dt.to_period(code)
    data["series"] = data.get("period", pd.Series("All", index=data.index)).fillna("Unknown")
    periods = pd.period_range(data.bucket.min(), data.bucket.max(), freq=code)
    rows = []
    for series, part in data.groupby("series"):
        grouped = part.groupby("bucket")[metric]
        values = grouped.sum(min_count=1) if aggregation == "sum" else grouped.mean()
        counts = grouped.count()
        for bucket in periods:
            rows.append({"period_start": bucket.start_time.date(), "series": series,
                         "value": values.get(bucket, np.nan), "observations": int(counts.get(bucket, 0))})
    return pd.DataFrame(rows)


def trend_statistics(table):
    summaries = []
    for series, group in table.groupby("series"):
        valid = group.dropna(subset=["value"]).sort_values("period_start")
        if valid.empty:
            continue
        dates = pd.to_datetime(valid.period_start)
        x = (dates - dates.min()).dt.days.to_numpy()
        slope = float(np.polyfit(x, valid.value, 1)[0]) if len(valid) >= 3 and x.max() > 0 else None
        summaries.append({"series": series, "observed_periods": len(valid),
                          "last_period": valid.iloc[-1].period_start,
                          "last_value": float(valid.iloc[-1].value),
                          "previous_period": valid.iloc[-2].period_start if len(valid) >= 2 else None,
                          "change": float(valid.iloc[-1].value - valid.iloc[-2].value) if len(valid) >= 2 else None,
                          "slope_per_day": slope})
    return summaries


def evidence_packet(frame, metric, table, scope, batches=None, logs=None, as_of=None):
    summaries = {}
    numeric = [c for c in frame.columns if c not in {"day", "pond", "period", "region", "source_ref", "batch_id", "id"}
               and pd.api.types.is_numeric_dtype(frame[c])]
    for key in numeric:
        values = frame[key].replace([np.inf, -np.inf], np.nan).dropna()
        summaries[key] = {"observations": len(values), "missing": len(frame) - len(values),
                          "mean": float(values.mean()) if len(values) else None,
                          "min": float(values.min()) if len(values) else None,
                          "max": float(values.max()) if len(values) else None}
    packet = {
        "SCOPE": scope,
        "DATA_QUALITY": {"rows_in_selected_period": len(frame), "ponds": frame.pond.nunique(),
                         "note": "Missing observations are not zeros. Means are observation-weighted, not pond-weighted. No causal claims or forecasts are supported."},
        "MEASUREMENTS": summaries,
        "TREND": {"metric": metric, "statistics": trend_statistics(table),
                  "recent_periods": table.tail(36).to_dict("records"), "total_period_rows": len(table)},
    }
    if batches is not None:
        metrics = batch_metrics(batches, logs, as_of)
        packet["KPI"] = {"as_of": as_of, "basis": "Cumulative since stocking; biomass estimated using latest sample; FCR aligned to sample date.",
                         "fish_remaining": int(metrics.fish_remaining.sum()),
                         "biomass_kg": float(metrics.biomass_kg.sum()),
                         "feed_kg": float(metrics.feed_kg.sum()), "harvest_kg": float(metrics.harvest_kg.sum()),
                         "batch_count": len(metrics), "first_20_batches": metrics.head(20).to_dict("records")}
    # pandas produces standards-compliant nulls for NaN and serializes dates.
    return json.loads(pd.Series(packet).to_json(date_format="iso"))
