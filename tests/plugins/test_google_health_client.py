from __future__ import annotations

import pytest

from plugins.google_health import client as gh


def test_error_hierarchy():
    assert issubclass(gh.GoogleHealthAuthRequiredError, gh.GoogleHealthError)
    assert issubclass(gh.GoogleHealthAPIError, gh.GoogleHealthError)
    err = gh.GoogleHealthAPIError("boom", status_code=429, response_body="{}")
    assert err.status_code == 429
    assert err.response_body == "{}"
    assert str(err) == "boom"


def test_client_init_resolves_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gh,
        "resolve_google_health_runtime_credentials",
        lambda **kwargs: {
            "access_token": "tok",
            "base_url": "https://health.googleapis.com/v4",
        },
    )
    client = gh.GoogleHealthClient()
    assert client.base_url == "https://health.googleapis.com/v4"


def test_client_init_raises_when_auth_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from hermes_cli.auth import AuthError

    def raise_(**kwargs):
        raise AuthError("not authenticated")

    monkeypatch.setattr(gh, "resolve_google_health_runtime_credentials", raise_)
    with pytest.raises(gh.GoogleHealthAuthRequiredError):
        gh.GoogleHealthClient()
