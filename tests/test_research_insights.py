from datetime import date
import json

import pandas as pd
import pytest

from farm.auth import Actor
from farm.db import initialize, make_engine
from farm.insights import evidence_packet, trend_table
from farm.llm import ask, configuration
from farm.services import add_pond
from farm.water import add_visit, read_visits


@pytest.fixture
def demo(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("APP_MODE", "demo")
    engine = make_engine("sqlite:///:memory:")
    initialize(engine)
    return engine, Actor(-1)


def test_missing_periods_stay_missing_and_morning_evening_separate():
    frame = pd.DataFrame({"day": [date(2026, 8, 1), date(2026, 8, 3), date(2026, 8, 1)],
                          "period": ["Morning", "Morning", "Evening"], "oxygen": [2, 4, 10]})
    table = trend_table(frame, "oxygen", "Daily")
    missing = table[(table.period_start == date(2026, 8, 2)) & (table.series == "Morning")].iloc[0]
    assert pd.isna(missing.value)
    assert missing.observations == 0
    assert table[(table.series == "Evening") & (table.period_start == date(2026, 8, 1))].iloc[0].value == 10


def test_native_multiple_water_visits_and_validation(demo):
    engine, actor = demo
    pond = add_pond(engine, "North", 100, 1)
    add_visit(engine, actor, pond, date.today(), "07:00", "Morning", oxygen=3, nh3=0.03)
    add_visit(engine, actor, pond, date.today(), "17:00", "Evening", oxygen=8)
    assert len(read_visits(engine, actor)) == 2
    with pytest.raises(ValueError):
        add_visit(engine, actor, pond, date.today(), "24:00", "Other", oxygen=3)


def test_llm_packet_and_request_are_read_only(demo, monkeypatch):
    engine, actor = demo
    frame = pd.DataFrame({"day": [date(2026, 8, 1)], "pond": ["North"], "oxygen": [3.0],
                          "notes": ["secret field note"], "observer": ["Private name"]})
    evidence = evidence_packet(frame, "oxygen", trend_table(frame, "oxygen"), {"source": "test"})
    serialized = json.dumps(evidence, allow_nan=False)
    assert "secret field note" not in serialized and "Private name" not in serialized
    captured = {}
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, _): yield b'{"message":{"content":"Oxygen is 3 mg/L [MEASUREMENTS]."}}'
    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()
    monkeypatch.setattr("farm.llm.requests.post", post)
    config = {"provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "test", "local": True}
    answer = ask(engine, actor, "Summarize", evidence, [], config)
    assert "[MEASUREMENTS]" in answer
    assert "tools" not in captured["json"]
    assert captured["allow_redirects"] is False
    assert captured["url"].endswith("/api/chat")


def test_remote_inference_requires_https(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://example.com/v1")
    with pytest.raises(ValueError, match="HTTPS"):
        configuration()


def test_kpi_trends_use_history_and_stop_at_end_date(demo):
    from datetime import timedelta
    from farm.services import add_batch, read_data, save_log
    from farm.insights import kpi_trend
    engine, _ = demo
    pond = add_pond(engine, "History", 100, 1)
    start = date.today() - timedelta(days=10)
    batch = add_batch(engine, pond, "History batch", "Tilapia", start, 100, 100)
    save_log(engine, batch, start + timedelta(days=2), feed_kg=10, weight_g=200)
    save_log(engine, batch, date.today(), deaths=20)
    _, batches, logs = read_data(engine)
    end = date.today() - timedelta(days=1)
    trend = kpi_trend(batches, logs, start, end, "fish_remaining", "Weekly")
    assert all(trend.value == 100)
    assert max(trend.snapshot_as_of) == end
