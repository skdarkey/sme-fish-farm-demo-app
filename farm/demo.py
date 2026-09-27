from datetime import date, timedelta
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from farm.models import Batch, DailyLog, Pond


def seed_demo(engine):
    """Explicit, all-or-nothing seeding of an empty demo database."""
    rng = random.Random(42)
    with Session(engine) as session, session.begin():
        if session.scalar(select(Pond.id).limit(1)):
            return False
        for index, (name, species, count, initial) in enumerate([
            ("North pond", "Tilapia", 8000, 35),
            ("East pond", "Tilapia", 6000, 50),
            ("South pond", "Catfish", 5000, 65),
        ]):
            pond = Pond(name=name, area_m2=1200 + index * 300, depth_m=1.5)
            session.add(pond)
            session.flush()
            start = date.today() - timedelta(days=60)
            batch = Batch(pond_id=pond.id, name=f"Cycle {index + 1:02d}", species=species,
                          stocked_on=start, stocked_count=count, initial_weight_g=initial)
            session.add(batch)
            session.flush()
            for age in range(1, 61):
                weight = initial + age * (2.1 + index * 0.3)
                session.add(DailyLog(batch_id=batch.id, day=start + timedelta(days=age),
                    feed_kg=round(count * (2.1 + index * 0.3) / 1000 * rng.uniform(1.2, 1.5), 2),
                    deaths=rng.randint(0, 5), harvest_count=0, harvest_kg=0,
                    weight_g=weight if age % 7 == 0 or age == 60 else None,
                    oxygen=3.6 if index == 1 and age == 60 else round(rng.uniform(4.8, 7.2), 1),
                    ph=round(rng.uniform(6.8, 8.1), 1), temperature=round(rng.uniform(25, 29), 1),
                    notes="Synthetic demonstration data"))
    return True
