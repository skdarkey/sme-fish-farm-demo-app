from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_demo_navigation_and_daily_save(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setattr("farm.db.settings", lambda: ("demo", "sqlite:///" + (tmp_path / "ui.db").as_posix()))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    next(b for b in app.button if b.label == "Load sample farm").click().run()
    assert not app.exception
    assert len(app.metric) == 4
    for page in ["Reports", "Water visits", "Advanced insights", "FWI data", "User access", "Ponds & stocking", "Daily records"]:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception
    next(c for c in app.checkbox if c.label.startswith("Replace")).check()
    next(b for b in app.button if b.label == "Save daily record").click().run()
    assert not app.exception
    assert any("Saved successfully" in item.value for item in app.success)
    app.sidebar.radio[0].set_value("Overview").run()
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    assert any("No stocked batches" in item.value for item in app.info)


def test_insights_kpis_and_native_water_form(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("APP_MODE", "demo")
    monkeypatch.setattr("farm.db.settings", lambda: ("demo", "sqlite:///" + (tmp_path / "insights.db").as_posix()))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30).run()
    next(b for b in app.button if b.label == "Load sample farm").click().run()
    app.sidebar.radio[0].set_value("Advanced insights").run()
    next(s for s in app.selectbox if s.label == "Metric").set_value("fcr").run()
    assert not app.exception
    assert any("snapshots" in s.value for s in app.subheader)
    app.sidebar.radio[0].set_value("Water visits").run()
    next(n for n in app.number_input if n.label == "Dissolved oxygen (mg/L)").set_value(4.5)
    next(b for b in app.button if b.label == "Save water visit").click().run()
    assert not app.exception
    assert any("Water visit saved" in item.value for item in app.success)
    app.sidebar.radio[0].set_value("Advanced insights").run()
    next(s for s in app.selectbox if s.label == "Data source").set_value("Pond water visits").run()
    assert not app.exception


def test_manager_user_access_page(tmp_path, monkeypatch):
    from sqlalchemy.orm import Session
    from farm.auth import register_identity
    from farm.db import initialize, make_engine
    from farm.models import AppUser
    path = "sqlite:///" + (tmp_path / "users.db").as_posix()
    engine = make_engine(path)
    initialize(engine)
    actor = register_identity(engine, {"iss": "test", "sub": "manager", "name": "Manager"})
    worker = register_identity(engine, {"iss": "test", "sub": "worker", "name": "Worker"})
    with Session(engine) as session, session.begin():
        session.get(AppUser, actor.user_id).role = "manager"
    monkeypatch.setattr("farm.db.settings", lambda: ("demo", path))
    monkeypatch.setattr("farm.auth_ui.sign_in", lambda _: actor)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
    app.sidebar.radio[0].set_value("User access").run()
    assert not app.exception
    next(s for s in app.selectbox if s.label == "Role").set_value("stocktaker")
    next(b for b in app.button if b.label == "Save access").click().run()
    assert not app.exception
    with Session(engine) as session:
        assert session.get(AppUser, worker.user_id).role == "stocktaker"
    engine.dispose()


def test_default_oidc_stops_before_farm_data(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setattr("farm.db.settings", lambda: ("demo", "sqlite:///" + (tmp_path / "closed.db").as_posix()))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.secrets["auth"] = {}
    app.run()
    assert not app.exception
    assert not app.metric
    assert not app.sidebar.radio
    assert any("Sign-in is temporarily unavailable" in message.value for message in app.info)


def test_named_google_login_uses_named_provider(tmp_path, monkeypatch):
    from test_auth_config import config
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setattr("farm.db.settings", lambda: ("demo", "sqlite:///" + (tmp_path / "google.db").as_posix()))
    calls = []
    monkeypatch.setattr("farm.auth_ui.st.login", lambda provider: calls.append(provider))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py")
    app.secrets["auth"] = config()
    app.run()
    assert not app.exception
    next(b for b in app.button if b.label == "Sign in with Google").click().run()
    assert not app.exception
    assert calls == ["google"]


def test_stocktaker_only_sees_record_pages(tmp_path, monkeypatch):
    from sqlalchemy.orm import Session
    from farm.auth import register_identity
    from farm.db import initialize, make_engine
    from farm.models import AppUser
    path = "sqlite:///" + (tmp_path / "worker.db").as_posix()
    engine = make_engine(path)
    initialize(engine)
    actor = register_identity(engine, {"iss": "test", "sub": "stocktaker"})
    with Session(engine) as session, session.begin():
        session.get(AppUser, actor.user_id).role = "stocktaker"
    monkeypatch.setattr("farm.db.settings", lambda: ("demo", path))
    monkeypatch.setattr("farm.auth_ui.sign_in", lambda _: actor)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py").run()
    assert not app.exception
    assert app.sidebar.radio[0].options == ["Daily records", "Water visits"]
    assert not app.metric
    assert not any(button.label == "Load sample farm" for button in app.button)
    engine.dispose()
