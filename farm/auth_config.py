"""Validate OIDC structure without exposing credential values in errors."""
from collections.abc import Mapping
from urllib.parse import urlparse


def login_providers(auth):
    if not isinstance(auth, Mapping) or not auth:
        return []
    for key in ("redirect_uri", "cookie_secret"):
        value = auth.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Set {key} in the shared [auth] section.")
    redirect = urlparse(auth["redirect_uri"])
    if not redirect.hostname or redirect.path != "/oauth2callback" or redirect.scheme not in {"http", "https"}:
        raise ValueError("The shared auth.redirect_uri must be an absolute URL ending in /oauth2callback.")
    if len(auth["cookie_secret"]) < 32 or auth["cookie_secret"].startswith("REPLACE_"):
        raise ValueError("Replace auth.cookie_secret with a strong random secret of at least 32 characters.")
    providers = []
    if "client_id" in auth:
        providers.append((None, auth))
    providers.extend((name, values) for name, values in auth.items()
                     if isinstance(values, Mapping) and name != "client_kwargs")
    if not providers:
        raise ValueError("Add client credentials to [auth] or a named section such as [auth.google].")
    for name, values in providers:
        section = "auth" if name is None else f"auth.{name}"
        for key in ("client_id", "client_secret", "server_metadata_url"):
            value = values.get(key)
            if not isinstance(value, str) or not value.strip() or value == "xxx" or value.startswith("REPLACE_"):
                raise ValueError(f"Set a valid {key} in [{section}].")
        if urlparse(values["server_metadata_url"]).scheme != "https":
            raise ValueError(f"Use an HTTPS server_metadata_url in [{section}].")
    return [name for name, _ in providers]
