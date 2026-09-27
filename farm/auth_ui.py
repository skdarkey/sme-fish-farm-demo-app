import logging
import os

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitAuthError
from sqlalchemy import select
from sqlalchemy.orm import Session

from farm.auth import Actor, current_user, demo_allowed, register_identity, require, set_access
from farm.models import AccessAudit, AppUser
from farm.auth_config import login_providers

logger = logging.getLogger(__name__)


def sign_in(engine):
    mode = os.getenv("AUTH_MODE", "oidc")
    if mode == "demo":
        if not demo_allowed(engine):
            st.error("Demo authentication is allowed only with the local SQLite demo database.")
            st.stop()
        st.warning("Local demo access · authentication is disabled. Use AUTH_MODE=oidc for real farm data.")
        return Actor(-1)
    if mode != "oidc":
        st.error("AUTH_MODE must be oidc or demo.")
        st.stop()
    try:
        providers = login_providers(st.secrets.get("auth", {}))
    except FileNotFoundError:
        providers = []
    except ValueError as exc:
        logger.warning("Authentication configuration invalid: %s", exc)
        st.title("Sign in to Pondwise")
        st.error("Sign-in is temporarily unavailable. Please contact your administrator.")
        st.stop()
    if not providers:
        st.title("Sign in to Pondwise")
        logger.warning("No OIDC provider configured. See docs/AUTHENTICATION.md.")
        st.info("Sign-in is temporarily unavailable. Please contact your administrator.")
        st.stop()
    if not st.user.is_logged_in:
        st.title("Sign in to Pondwise")
        st.write("Sign in or register through your identity provider. New accounts require manager approval.")
        for provider in providers:
            label = "Sign in / Register" if provider is None else f"Sign in with {provider.title()}"
            if st.button(label, type="primary"):
                try:
                    st.login(provider)
                except StreamlitAuthError:
                    logger.warning("Unable to initiate OIDC login. Check provider configuration.")
                    st.error("Unable to start sign-in. Please try again or contact your administrator.")
        st.stop()
    st.sidebar.button("Sign out", on_click=st.logout)
    try:
        actor = register_identity(engine, st.user.to_dict())
        user = current_user(engine, actor)
    except (ValueError, PermissionError) as exc:
        st.error(str(exc))
        st.stop()
    identity = str(actor.user_id)
    if st.session_state.get("signed_in_identity") != identity:
        for key in list(st.session_state):
            if key.startswith("chat_"):
                del st.session_state[key]
        st.session_state["signed_in_identity"] = identity
    if user["role"] == "pending":
        st.title("Access requested")
        st.info("Your account is registered. A manager must approve your role before you can access farm data.")
        with st.expander("Identity details for your administrator"):
            st.json({"user_id": actor.user_id, "issuer": st.user.get("iss"), "subject": st.user.get("sub")})
        st.stop()
    st.sidebar.caption(f"{user['name'] or user['email']} · {user['role'].title()}")
    return actor


def render_users(engine, actor):
    require(engine, actor, "users")
    st.title("User access")
    st.caption("Stocktakers record daily activity and water visits. Managers also access analytics, imports, setup, and user administration.")
    if actor.user_id == -1:
        st.info("Account administration is available after OIDC sign-in. Demo mode cannot approve users.")
        return
    with Session(engine) as session:
        users = pd.DataFrame([{k: getattr(u, k) for k in ["id", "name", "email", "role", "active", "registered_at"]}
                              for u in session.scalars(select(AppUser))])
    st.dataframe(users, hide_index=True, width="stretch")
    candidates = users[users.id != actor.user_id]
    if not candidates.empty:
        labels = {int(r.id): f"{r.id}: {r['name']} ({r.email})" for _, r in candidates.iterrows()}
        target = st.selectbox("Account", list(labels), format_func=labels.get)
        row = candidates[candidates.id == target].iloc[0]
        with st.form(f"access_{target}"):
            roles = ["pending", "stocktaker", "manager"]
            role = st.selectbox("Role", roles, index=roles.index(row.role))
            active = st.checkbox("Account enabled", value=bool(row.active))
            if st.form_submit_button("Save access", type="primary"):
                try:
                    set_access(engine, actor, target, role, active)
                except (ValueError, PermissionError) as exc:
                    st.error(str(exc))
                else:
                    st.success("Access updated. Permissions are checked on the user's next interaction.")
                    st.rerun()
    with engine.connect() as conn:
        audit = pd.read_sql(select(AccessAudit).order_by(AccessAudit.id.desc()).limit(100), conn)
    with st.expander("Recent access changes"):
        st.dataframe(audit, hide_index=True, width="stretch")
