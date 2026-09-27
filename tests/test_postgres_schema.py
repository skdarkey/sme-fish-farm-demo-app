from sqlalchemy import create_mock_engine

from farm.models import Base


def test_schema_compiles_for_postgresql():
    statements = []
    engine = create_mock_engine("postgresql+psycopg://", lambda sql, *args, **kwargs:
                                statements.append(str(sql.compile(dialect=engine.dialect))))
    Base.metadata.create_all(engine)
    ddl = "\n".join(statements)
    assert "CREATE TABLE daily_logs" in ddl
    assert "UNIQUE (batch_id, day)" in ddl
    assert "FOREIGN KEY(batch_id) REFERENCES batches (id)" in ddl
