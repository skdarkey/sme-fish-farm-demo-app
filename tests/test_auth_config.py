import pytest

from farm.auth_config import login_providers


def config():
    return {"redirect_uri": "http://localhost:8501/oauth2callback", "cookie_secret": "a" * 64,
            "google": {"client_id": "test.apps.googleusercontent.com", "client_secret": "test-secret",
                       "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration"}}


def test_named_google_and_default_are_supported():
    auth = config()
    assert login_providers(auth) == ["google"]
    google = auth.pop("google")
    auth.update(google)
    assert login_providers(auth) == [None]


def test_placeholder_cookie_rejected_without_exposing_values():
    auth = config()
    auth["cookie_secret"] = "xxx"
    with pytest.raises(ValueError, match="strong random"):
        login_providers(auth)


def test_missing_provider_setting_reports_key_only():
    auth = config()
    del auth["google"]["client_secret"]
    with pytest.raises(ValueError, match=r"client_secret in \[auth.google\]"):
        login_providers(auth)


def test_no_configuration_returns_no_providers():
    assert login_providers({}) == []
