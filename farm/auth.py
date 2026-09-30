"""OIDC identity registration and server-side role checks, independent of UI."""
from dataclasses import dataclass
import os
import time
import math

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from farm.models import AccessAudit, AppUser

PAGES = {
    "Overview": "analyze",
    "Daily records": "record", "Water visits": "record",
    "Ponds & stocking": "manage",
    "Reports": "analyze", "Advanced insights": "analyze",
    "User access": "users",
}
ROLE_PERMISSIONS = {"pending": set(), "stocktaker": {"record"},
                    "manager": {"record", "analyze", "manage", "users"}}


@dataclass(frozen=True)
class Actor:
    user_id: int


def demo_allowed(engine):
    return (os.getenv("AUTH_MODE", "oidc") == "demo" and
            os.getenv("APP_MODE", "demo") == "demo" and engine.dialect.name == "sqlite")


def current_user(engine, actor):
    if actor.user_id == -1 and demo_allowed(engine):
        return {"id": -1, "name": "Local demo manager", "email": "", "role": "manager", "active": True}
    with Session(engine) as session:
        user = session.get(AppUser, actor.user_id)
        if user is None or not user.active:
            raise PermissionError("Your account is disabled or no longer registered.")
        return {key: getattr(user, key) for key in ("id", "name", "email", "role", "active")}


def require(engine, actor, permission):
    user = current_user(engine, actor)
    if permission not in ROLE_PERMISSIONS.get(user["role"], set()):
        raise PermissionError("Your role does not permit this action.")
    return user


def pages_for(engine, actor):
    role = current_user(engine, actor)["role"]
    return [p for p, permission in PAGES.items() if permission in ROLE_PERMISSIONS[role]]


def register_identity(engine, claims):
    issuer, subject = claims.get("iss"), claims.get("sub")
    if not isinstance(issuer, str) or not isinstance(subject, str) or not issuer or not subject:
        raise ValueError("The identity provider must supply iss and sub claims.")
    if len(issuer) > 255 or len(subject) > 255:
        raise ValueError("Identity claims exceed the supported length.")
    expiry = claims.get("exp")
    if expiry is not None:
        try:
            expired = not math.isfinite(float(expiry)) or float(expiry) <= time.time()
        except (TypeError, ValueError):
            raise ValueError("Invalid identity expiry.") from None
        if expired:
            raise ValueError("Your sign-in has expired. Sign out and sign in again.")
    # Never trust roles, email matching, or URL parameters to grant access.
    def find(session):
        return session.scalar(select(AppUser).where(AppUser.issuer == issuer, AppUser.subject == subject))
    try:
        with Session(engine) as session, session.begin():
            user = find(session)
            if user is None:
                user = AppUser(issuer=issuer, subject=subject,
                               email=str(claims.get("email", ""))[:255],
                               name=str(claims.get("name", ""))[:255], role="pending")
                session.add(user)
                session.flush()
            return Actor(user.id)
    except IntegrityError:
        # Simultaneous first logins resolve to the same registered identity.
        with Session(engine) as session:
            user = find(session)
            if user is None:
                raise
            return Actor(user.id)


def set_access(engine, actor, target_id, role, active):
    require(engine, actor, "users")
    if actor.user_id == -1:
        raise PermissionError("Demo mode cannot administer real accounts.")
    if role not in ROLE_PERMISSIONS:
        raise ValueError("Unknown role.")
    if actor.user_id == target_id:
        raise ValueError("You cannot change your own access.")
    with Session(engine) as session, session.begin():
        target = session.get(AppUser, target_id)
        if target is None:
            raise ValueError("User not found.")
        before = f"{target.role}, active={target.active}"
        target.role, target.active = role, bool(active)
        session.add(AccessAudit(actor=str(actor.user_id), target_id=target_id,
                                change=f"{before} -> {role}, active={bool(active)}"))


def authorize_write(engine, actor, action, *args, **kwargs):
    from farm.services import add_batch, add_pond, save_log
    permission = {add_batch: "manage", add_pond: "manage", save_log: "record"}.get(action)
    if permission is None:
        raise PermissionError("Unknown write action.")
    require(engine, actor, permission)
    return action(engine, *args, **kwargs)
