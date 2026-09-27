from pathlib import Path

from streamlit.testing.v1 import AppTest

from test_research_insights import fixture_files


def test_import_and_research_insights_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("APP_MODE", "demo")
    local = tmp_path / "data" / "fwi-source"
    local.mkdir(parents=True)
    for name, content in fixture_files().items():
        (local / name).write_bytes(content)
    monkeypatch.setattr("farm.fwi_ui.ROOT", tmp_path)
    monkeypatch.setattr("farm.db.settings", lambda: ("demo", "sqlite:///" + (tmp_path / "research.db").as_posix()))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    app.sidebar.radio[0].set_value("FWI data").run()
    next(b for b in app.button if b.label == "Import this snapshot").click().run()
    assert not app.exception
    assert any("imported" in item.value for item in app.success)
    for table in ["water_quality.csv", "stocking_harvest.csv", "dropouts.csv"]:
        next(s for s in app.selectbox if s.label == "Source table").set_value(table).run()
        assert not app.exception
    app.sidebar.radio[0].set_value("Advanced insights").run()
    next(s for s in app.selectbox if s.label == "Data source").set_value("FWI research snapshot").run()
    assert not app.exception
    assert any("Ask your farm data" in s.value for s in app.subheader)
