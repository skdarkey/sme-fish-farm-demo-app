from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from farm.analytics import batch_metrics, water_alerts
from farm.db import initialize, make_engine
from farm.models import DailyLog
from farm.services import add_batch, add_pond, read_data, save_log


@pytest.fixture
def farm():
    engine = make_engine("sqlite:///:memory:")
    initialize(engine)
    pond = add_pond(engine, "North", 1000, 1.5)
    start = date.today() - timedelta(days=10)
    batch = add_batch(engine, pond, "Cycle 1", "Tilapia", start, 1000, 100)
    return engine, batch, start


def test_inventory_and_harvest_adjusted_fcr(farm):
    engine, batch, start = farm
    save_log(engine, batch, start + timedelta(days=5), feed_kg=100, deaths=10,
             harvest_count=100, harvest_kg=20, weight_g=200)
    save_log(engine, batch, start + timedelta(days=6), feed_kg=50, deaths=5)
    _, batches, logs = read_data(engine)
    row = batch_metrics(batches, logs, date.today()).iloc[0]
    assert row.fish_remaining == 885
    assert row.biomass_kg == 177
    assert row.survival_pct == 98.5
    assert row.fcr == pytest.approx(100 / 98)
    historical = batch_metrics(batches, logs, start + timedelta(days=5)).iloc[0]
    assert historical.fish_remaining == 890
    assert historical.feed_kg == 100


def test_replace_is_explicit_and_cannot_overdraw_stock(farm):
    engine, batch, start = farm
    save_log(engine, batch, start, deaths=100)
    with pytest.raises(ValueError, match="already has"):
        save_log(engine, batch, start, deaths=20)
    save_log(engine, batch, start, deaths=20, replace=True)
    with pytest.raises(ValueError, match="exceed"):
        save_log(engine, batch, start + timedelta(days=1), deaths=981)
    assert read_data(engine)[2].deaths.sum() == 20


def test_backdated_depletion_rejects_later_logs(farm):
    engine, batch, start = farm
    save_log(engine, batch, start + timedelta(days=2), feed_kg=10)
    with pytest.raises(ValueError, match="later logs"):
        save_log(engine, batch, start, harvest_count=1000, harvest_kg=100)


@pytest.mark.parametrize("values", [dict(feed_kg=-1), dict(feed_kg=float("nan")),
    dict(deaths=1.5), dict(ph=15), dict(oxygen=-1), dict(harvest_count=1), dict(weight_g=0)])
def test_invalid_measurements(farm, values):
    engine, batch, start = farm
    with pytest.raises(ValueError):
        save_log(engine, batch, start, **values)
    assert read_data(engine)[2].empty


def test_dates_and_no_growth(farm):
    engine, batch, start = farm
    for day in [start - timedelta(days=1), date.today() + timedelta(days=1)]:
        with pytest.raises(ValueError):
            save_log(engine, batch, day)
    save_log(engine, batch, start, weight_g=90, feed_kg=10)
    _, batches, logs = read_data(engine)
    assert batch_metrics(batches, logs, date.today()).iloc[0].fcr is None
    assert batch_metrics(batches, logs, start - timedelta(days=1)).empty


def test_latest_water_reading_per_parameter(farm):
    engine, batch, start = farm
    save_log(engine, batch, start, oxygen=3, ph=7)
    save_log(engine, batch, start + timedelta(days=1), ph=9)
    logs = read_data(engine)[2]
    alerts = water_alerts(logs, {batch: "Cycle 1"}, date.today())
    assert len(alerts) == 2
    assert str(start) in alerts[0]


def test_database_enforces_unique_daily_record(farm):
    engine, batch, start = farm
    save_log(engine, batch, start)
    with pytest.raises(IntegrityError), Session(engine) as session, session.begin():
        session.add(DailyLog(batch_id=batch, day=start))


def test_demo_seed_is_idempotent():
    from farm.demo import seed_demo
    engine = make_engine("sqlite:///:memory:")
    initialize(engine)
    assert seed_demo(engine)
    assert not seed_demo(engine)
    ponds, batches, logs = read_data(engine)
    assert (len(ponds), len(batches), len(logs)) == (3, 3, 180)
