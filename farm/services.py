"""Transactional writes. Every daily write locks its batch on PostgreSQL."""
import math
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from farm.models import Batch, DailyLog, Pond


def number(value, label, minimum=0, maximum=None, integer=False):
    if not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"{label} must be between {minimum} and {maximum or 'a valid upper value'}.")
    if integer and int(value) != value:
        raise ValueError(f"{label} must be a whole number.")


def label(value, field, limit=100):
    value = value.strip()
    if not value or len(value) > limit:
        raise ValueError(f"{field} must contain 1–{limit} characters.")
    return value


def add_pond(engine, name, area_m2, depth_m):
    name = label(name, "Pond name")
    number(area_m2, "Area", 0.01)
    number(depth_m, "Depth", 0.01)
    with Session(engine) as session, session.begin():
        if session.scalar(select(Pond.id).where(func.lower(Pond.name) == name.lower())):
            raise ValueError("A pond with this name already exists.")
        pond = Pond(name=name, area_m2=area_m2, depth_m=depth_m)
        session.add(pond)
        session.flush()
        return pond.id


def add_batch(engine, pond_id, name, species, stocked_on, stocked_count, initial_weight_g):
    name, species = label(name, "Batch name"), label(species, "Species")
    number(stocked_count, "Stocked fish", 1, integer=True)
    number(initial_weight_g, "Initial weight", 0.01)
    if stocked_on > date.today():
        raise ValueError("Stocking date cannot be in the future.")
    with Session(engine) as session, session.begin():
        if not session.get(Pond, pond_id):
            raise ValueError("Select an existing pond.")
        if session.scalar(select(Batch.id).where(func.lower(Batch.name) == name.lower())):
            raise ValueError("A batch with this name already exists.")
        batch = Batch(pond_id=pond_id, name=name, species=species, stocked_on=stocked_on,
                      stocked_count=stocked_count, initial_weight_g=initial_weight_g)
        session.add(batch)
        session.flush()
        return batch.id


def save_log(engine, batch_id, day, *, feed_kg=0.0, deaths=0, harvest_count=0,
             harvest_kg=0.0, weight_g=None, oxygen=None, ph=None, temperature=None,
             notes="", replace=False):
    for key, value in {"Feed": feed_kg, "Deaths": deaths, "Harvest count": harvest_count,
                       "Harvest weight": harvest_kg}.items():
        number(value, key, integer=key in {"Deaths", "Harvest count"})
    for key, value, low, high in [("Weight", weight_g, 0.01, None), ("Oxygen", oxygen, 0, None),
                                  ("pH", ph, 0, 14), ("Temperature", temperature, 0, 50)]:
        if value is not None:
            number(value, key, low, high)
    if (harvest_count > 0) != (harvest_kg > 0):
        raise ValueError("Harvest count and harvest weight must both be supplied.")
    if len(notes) > 1000:
        raise ValueError("Notes must be at most 1,000 characters.")
    with Session(engine) as session, session.begin():
        batch = session.scalar(select(Batch).where(Batch.id == batch_id).with_for_update())
        if batch is None:
            raise ValueError("Select an existing batch.")
        if not batch.stocked_on <= day <= date.today():
            raise ValueError("Log date must be between stocking and today.")
        existing = session.scalar(select(DailyLog).where(DailyLog.batch_id == batch_id, DailyLog.day == day))
        if existing and not replace:
            raise ValueError("This date already has a log. Enable replacement to correct it.")
        others = list(session.scalars(select(DailyLog).where(DailyLog.batch_id == batch_id)))
        removed = sum(r.deaths + r.harvest_count for r in others if r.day != day)
        if removed + deaths + harvest_count > batch.stocked_count:
            raise ValueError("Deaths and harvests would exceed the number of stocked fish.")
        removed_before = sum(r.deaths + r.harvest_count for r in others if r.day < day)
        if removed_before == batch.stocked_count:
            raise ValueError("This batch had no fish remaining at the start of this date.")
        # Corrections must not leave later operational records after complete depletion.
        timeline = [(r.day, r.deaths + r.harvest_count) for r in others if r.day != day]
        timeline.append((day, deaths + harvest_count))
        remaining = batch.stocked_count
        for _, removals in sorted(timeline):
            if remaining == 0:
                raise ValueError("This would leave later logs after the batch was fully depleted.")
            remaining -= removals
        row = existing or DailyLog(batch_id=batch_id, day=day)
        for key, value in dict(feed_kg=feed_kg, deaths=deaths, harvest_count=harvest_count,
                               harvest_kg=harvest_kg, weight_g=weight_g, oxygen=oxygen,
                               ph=ph, temperature=temperature, notes=notes.strip()).items():
            setattr(row, key, value)
        session.add(row)


def read_data(engine):
    import pandas as pd
    with engine.connect() as connection:
        return tuple(pd.read_sql(select(model), connection) for model in (Pond, Batch, DailyLog))
