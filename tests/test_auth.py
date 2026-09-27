import time

import pytest
from sqlalchemy.orm import Session

from farm.auth import Actor, authorize_write, current_user, pages_for, register_identity, require, set_access
from farm.db import initialize, make_engine
from farm.models import AppUser
from farm.services import add_pond


@pytest.fixture
def accounts():
    engine = make_engine("sqlite:///:memory:")
    initialize(engine)
    manager = register_identity(engine, {"iss": "https://issuer", "sub": "m", "email": "same@example.org"})
    worker = register_identity(engine, {"iss": "https://issuer", "sub": "s", "email": "same@example.org", "role": "manager"})
    with Session(engine) as session, session.begin():
        session.get(AppUser, manager.user_id).role = "manager"
    return engine, manager, worker


def test_registration_is_pending_and_does_not_trust_email_or_claim_role(accounts):
    engine, manager, worker = accounts
    assert worker.user_id != manager.user_id
    assert current_user(engine, worker)["role"] == "pending"
    assert pages_for(engine, worker) == []
    assert register_identity(engine, {"iss": "https://issuer", "sub": "s"}) == worker
    assert register_identity(engine, {"iss": "https://other", "sub": "s"}) != worker


def test_stocktaker_permissions_and_revocation(accounts):
    engine, manager, worker = accounts
    set_access(engine, manager, worker.user_id, "stocktaker", True)
    assert pages_for(engine, worker) == ["Daily records", "Water visits"]
    require(engine, worker, "record")
    for permission in ["manage", "analyze", "import", "users"]:
        with pytest.raises(PermissionError):
            require(engine, worker, permission)
    with pytest.raises(PermissionError):
        authorize_write(engine, worker, add_pond, "No", 10, 1)
    with pytest.raises(PermissionError):
        set_access(engine, worker, worker.user_id, "manager", True)
    set_access(engine, manager, worker.user_id, "stocktaker", False)
    with pytest.raises(PermissionError):
        require(engine, worker, "record")


def test_manager_cannot_demote_self(accounts):
    engine, manager, _ = accounts
    with pytest.raises(ValueError, match="own access"):
        set_access(engine, manager, manager.user_id, "pending", False)


def test_invalid_and_expired_identity(accounts):
    engine, _, _ = accounts
    for claims in [{}, {"iss": "i", "sub": "s", "exp": time.time() - 1}, {"iss": "i", "sub": "s", "exp": "bad"}]:
        with pytest.raises(ValueError):
            register_identity(engine, claims)


def test_no_implicit_demo_bypass(accounts, monkeypatch):
    engine, _, _ = accounts
    monkeypatch.delenv("AUTH_MODE", raising=False)
    with pytest.raises(PermissionError):
        require(engine, Actor(-1), "analyze")
    monkeypatch.setenv("AUTH_MODE", "demo")
    monkeypatch.setenv("APP_MODE", "postgres")
    with pytest.raises(PermissionError):
        require(engine, Actor(-1), "analyze")
