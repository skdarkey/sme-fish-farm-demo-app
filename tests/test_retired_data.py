from sqlalchemy import inspect, text
from farm.db import initialize, make_engine
from farm.services import add_pond
from scripts.remove_fwi_data import purge


def test_retired_data_purge_preserves_farm_records():
    engine = make_engine('sqlite:///:memory:')
    initialize(engine)
    add_pond(engine, 'Keep this pond', 100, 1)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE research_datasets (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE research_records (id INTEGER PRIMARY KEY, dataset_id INTEGER REFERENCES research_datasets(id))'))
        connection.execute(text('INSERT INTO research_datasets VALUES (1)'))
        connection.execute(text('INSERT INTO research_records VALUES (1, 1)'))
    assert purge(engine)['ponds'] == 1
    assert not {'research_records', 'research_datasets'} & set(inspect(engine).get_table_names())
    assert purge(engine)['ponds'] == 1
    engine.dispose()
