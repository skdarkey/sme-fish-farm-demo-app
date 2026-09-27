"""Lossless, versioned FWI import. Source observations never mutate inventory."""
import hashlib
from io import BytesIO
import json

import pandas as pd
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from farm.auth import require
from farm.models import ResearchDataset, ResearchRecord

SOURCE_URL = "https://github.com/fish-welfare-initiative/fwi-farm-data-india"
SOURCE_COMMIT = "971491084b5093f12cf2a32b0c7718c00323f4b0"
FILES = {"enrolled_ponds.csv": "Date of data collection", "water_quality.csv": "Date of data collection",
         "stocking_harvest.csv": "Event date", "dropouts.csv": "Date of drop out"}
WATER_METRICS = {
    "DO (mg/L)": "oxygen", "pH": "ph", "Temp (in °C)": "temperature",
    "Turbidity (in cm)": "secchi_cm", "Ammonia—TAN (NH3-N) (mg/L)": "tan_n",
    "Ammonia—TAN (NH3) (mg/L)": "tan_nh3", "Ammonia—NH3 (mg/L)": "nh3",
    "TDS (ppt)": "tds_ppt", "Alkalinity (mg/L)": "alkalinity", "Hardness (mg/L)": "hardness",
}
MISSING = {"", "NA", "N/A"}


def prepare_import(files, release):
    if set(files) != set(FILES):
        raise ValueError("Supply exactly enrolled_ponds.csv, water_quality.csv, stocking_harvest.csv and dropouts.csv.")
    if not release.strip() or len(release) > 100:
        raise ValueError("Supply a release label of 1–100 characters.")
    if sum(len(content) for content in files.values()) > 30_000_000:
        raise ValueError("The combined CSV size must not exceed 30 MB.")
    hashes, frames, rows, issues = {}, {}, [], []
    for name in sorted(FILES):
        content = files[name]
        hashes[name] = hashlib.sha256(content).hexdigest()
        try:
            frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False, encoding="utf-8-sig")
        except (ValueError, UnicodeError, pd.errors.ParserError) as exc:
            raise ValueError(f"Cannot parse {name} as UTF-8 CSV.") from exc
        expected = {"pond_id", "region", FILES[name]}
        if name == "water_quality.csv":
            expected |= set(WATER_METRICS) | {"Type", "Time of data collection"}
        if name == "stocking_harvest.csv":
            expected |= {"Type", "Fish harvested (total, in kg)"}
        if not expected.issubset(frame.columns):
            raise ValueError(f"{name} is missing columns: {', '.join(sorted(expected - set(frame.columns)))}")
        if len(frame) > 100_000:
            raise ValueError(f"{name} exceeds 100,000 records.")
        if frame.empty:
            raise ValueError(f"{name} contains no records. This importer expects a complete FWI snapshot.")
        if not frame.pond_id.str.fullmatch(r"ara2_[0-9a-f]{8}").all():
            raise ValueError(f"{name}: expected v3 ara2_ pond IDs. Do not join different release namespaces.")
        parsed = pd.to_datetime(frame[FILES[name]], format="%m/%d/%Y", errors="coerce")
        if parsed.isna().any():
            raise ValueError(f"{name}: invalid or missing dates (required format MM/DD/YYYY).")
        frames[name] = frame
        for row_number, (payload, observed_on) in enumerate(zip(frame.to_dict("records"), parsed.dt.date), start=2):
            rows.append(dict(file=name, row_number=row_number, external_pond_id=payload["pond_id"],
                             region=payload["region"], observed_on=observed_on, payload=payload))
    enrollment = frames["enrolled_ponds.csv"]
    duplicates = enrollment.pond_id.duplicated().sum()
    if duplicates:
        issues.append(f"{duplicates} additional enrollment row(s) for repeated pond IDs; all surveys preserved.")
    harvest = frames["stocking_harvest.csv"]
    missing_harvest = (harvest.Type.str.contains("harvest", case=False) & harvest["Fish harvested (total, in kg)"].isin(MISSING)).sum()
    issues.append(f"{missing_harvest} harvest event(s) have no recorded fish harvest weight; not treated as zero.")
    water = frames["water_quality.csv"]
    for field in WATER_METRICS:
        invalid = (~water[field].isin(MISSING) & pd.to_numeric(water[field], errors="coerce").isna()).sum()
        if invalid:
            issues.append(f"{field}: {invalid} nonnumeric observation(s); retained raw, excluded from numeric trends.")
    ponds = set().union(*(set(frame.pond_id) for frame in frames.values()))
    manifest = {"sha256": hashes, "rows": {name: len(frame) for name, frame in frames.items()},
                "ponds": len(ponds), "issues": issues, "date_format": "MM/DD/YYYY",
                "license": "CC-BY-4.0", "attribution": "Fish Welfare Initiative (2026), FWI Farm Data — India"}
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return {"release": release.strip(), "digest": digest, "manifest": manifest, "rows": rows}


def import_fwi(engine, actor, prepared):
    require(engine, actor, "import")
    with Session(engine) as session, session.begin():
        existing = session.scalar(select(ResearchDataset.id).where(ResearchDataset.digest == prepared["digest"]))
        if existing:
            return existing, False
        dataset = ResearchDataset(digest=prepared["digest"], release=prepared["release"],
                                  source=SOURCE_URL, manifest=prepared["manifest"])
        session.add(dataset)
        session.flush()
        for start in range(0, len(prepared["rows"]), 500):
            session.execute(insert(ResearchRecord), [dict(dataset_id=dataset.id, **row)
                            for row in prepared["rows"][start:start + 500]])
        return dataset.id, True


def datasets(engine, actor):
    require(engine, actor, "analyze")
    with engine.connect() as connection:
        return pd.read_sql(select(ResearchDataset), connection)


def read_research(engine, actor, dataset_id, file):
    require(engine, actor, "analyze")
    with Session(engine) as session:
        records = session.scalars(select(ResearchRecord).where(ResearchRecord.dataset_id == dataset_id, ResearchRecord.file == file))
        rows = [dict(r.payload, source_row=r.row_number, source_date=r.observed_on) for r in records]
    return pd.DataFrame(rows)


def water_frame(raw):
    result = pd.DataFrame({"day": raw.source_date, "pond": raw.pond_id,
                           "region": raw.region, "period": raw.Type.fillna("Unknown"),
                           "source_ref": raw.source_row.map(lambda n: f"water_quality.csv:row {n}")})
    for source, key in WATER_METRICS.items():
        values = pd.to_numeric(raw[source], errors="coerce")
        result[key] = values.where(values.map(lambda x: pd.isna(x) or abs(x) != float("inf")))
    return result
