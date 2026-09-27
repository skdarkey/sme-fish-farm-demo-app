import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event

from farm.models import Base

ROOT = Path(__file__).resolve().parents[1]


def settings():
    load_dotenv(ROOT / ".env")
    mode = os.getenv("APP_MODE", "demo").lower()
    if mode not in {"demo", "postgres"}:
        raise ValueError("APP_MODE must be demo or postgres.")
    if mode == "demo":
        (ROOT / "data").mkdir(exist_ok=True)
        return mode, "sqlite:///" + (ROOT / "data" / "demo.db").as_posix()
    url = os.getenv("DATABASE_URL", "")
    if not url.startswith("postgresql+psycopg://"):
        raise ValueError("Set DATABASE_URL to a postgresql+psycopg:// connection URL.")
    return mode, url


def make_engine(url):
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
    return engine


def initialize(engine):
    # Bootstrap new databases only; schema changes require a migration.
    Base.metadata.create_all(engine)
