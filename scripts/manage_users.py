"""Trusted operator CLI to bootstrap/recover a manager; not exposed in the web UI."""
import argparse

from sqlalchemy.orm import Session

from farm.auth import register_identity
from farm.db import initialize, make_engine, settings
from farm.models import AccessAudit, AppUser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--subject", required=True)
    args = parser.parse_args()
    _, url = settings()
    engine = make_engine(url)
    initialize(engine)
    actor = register_identity(engine, {"iss": args.issuer, "sub": args.subject})
    with Session(engine) as session, session.begin():
        user = session.get(AppUser, actor.user_id)
        user.role, user.active = "manager", True
        session.add(AccessAudit(actor="server operator CLI", target_id=user.id, change="Bootstrap/recovery: manager, active=True"))
    print(f"Manager access enabled for registered user {actor.user_id}.")


if __name__ == "__main__":
    main()
