"""Remove retired demonstration tables only; preserve operational tables."""
from sqlalchemy import inspect, text
from farm.db import make_engine, settings

TABLES = ("research_records", "research_datasets")


def purge(engine):
    before = {}
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        operational = sorted(tables - set(TABLES))
        for name in operational:
            quoted = connection.dialect.identifier_preparer.quote(name)
            before[name] = connection.scalar(text(f"SELECT COUNT(*) FROM {quoted}"))
        if engine.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA secure_delete=ON")
        for name in TABLES:
            if name in tables:
                # No CASCADE: unexpected external dependencies must stop removal.
                connection.exec_driver_sql(f'DROP TABLE "{name}"')
        for name, count in before.items():
            quoted = connection.dialect.identifier_preparer.quote(name)
            if connection.scalar(text(f"SELECT COUNT(*) FROM {quoted}")) != count:
                raise RuntimeError("Operational record count changed; purge aborted.")
    return before


if __name__ == "__main__":
    _, url = settings()
    engine = make_engine(url)
    try:
        print("Operational row counts preserved:", purge(engine))
    finally:
        engine.dispose()
