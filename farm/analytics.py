"""Pure analytics shared by the UI and reporting pipeline."""
import pandas as pd


def batch_metrics(batches, logs, as_of):
    rows = []
    for batch in batches.to_dict("records"):
        if batch["stocked_on"] > as_of:
            continue
        history = logs[(logs.batch_id == batch["id"]) & (logs.day <= as_of)].sort_values("day")
        deaths, harvested = int(history.deaths.sum()), int(history.harvest_count.sum())
        remaining = batch["stocked_count"] - deaths - harvested
        samples = history[history.weight_g.notna()]
        sample_day = samples.iloc[-1].day if not samples.empty else batch["stocked_on"]
        weight = float(samples.iloc[-1].weight_g) if not samples.empty else batch["initial_weight_g"]
        # FCR is aligned to the latest growth sample; later feed must not inflate it.
        measured = history[history.day <= sample_day]
        fish_at_sample = batch["stocked_count"] - measured.deaths.sum() - measured.harvest_count.sum()
        gain = fish_at_sample * weight / 1000 + measured.harvest_kg.sum() - batch["stocked_count"] * batch["initial_weight_g"] / 1000
        fcr = float(measured.feed_kg.sum() / gain) if gain > 0 and not samples.empty else None
        rows.append(dict(batch_id=batch["id"], batch=batch["name"], pond_id=batch["pond_id"],
                         species=batch["species"], fish_remaining=remaining,
                         survival_pct=100 * (batch["stocked_count"] - deaths) / batch["stocked_count"],
                         biomass_kg=remaining * weight / 1000, feed_kg=float(history.feed_kg.sum()),
                         harvest_kg=float(history.harvest_kg.sum()), deaths=deaths,
                         weight_g=weight, sample_day=sample_day, sample_age_days=(as_of - sample_day).days,
                         fcr=fcr))
    return pd.DataFrame(rows, columns=["batch_id", "batch", "pond_id", "species", "fish_remaining",
                                      "survival_pct", "biomass_kg", "feed_kg", "harvest_kg", "deaths",
                                      "weight_g", "sample_day", "sample_age_days", "fcr"])


def water_alerts(logs, batch_names, as_of, oxygen_min=4.0, ph_min=6.5, ph_max=8.5):
    alerts = []
    for batch_id, group in logs[logs.day <= as_of].groupby("batch_id"):
        for field, low, high, unit in [("oxygen", oxygen_min, None, "mg/L"), ("ph", ph_min, ph_max, "")]:
            readings = group[group[field].notna()].sort_values("day")
            if readings.empty:
                continue
            row = readings.iloc[-1]
            value = row[field]
            if value < low or (high is not None and value > high):
                alerts.append(f"{batch_names.get(batch_id, batch_id)} · {field}: {value:.1f} {unit} · reading {row.day}")
    return alerts
