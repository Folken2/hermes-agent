from __future__ import annotations

import pytest

from plugins.google_health import client as gh


class _FakeResponse:
    def __init__(self, status_code, payload=None, *, text="", headers=None):
        import json as _json
        self.status_code = status_code
        self._payload = payload
        self.text = text or (_json.dumps(payload) if payload is not None else "")
        self.headers = headers or {"content-type": "application/json"}
        self.content = self.text.encode("utf-8") if self.text else b""

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


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


def test_request_returns_json_on_200(monkeypatch):
    monkeypatch.setattr(
        gh, "resolve_google_health_runtime_credentials",
        lambda **k: {"access_token": "tok", "base_url": "https://health.googleapis.com/v4"},
    )
    monkeypatch.setattr(
        gh.httpx, "request",
        lambda *a, **k: _FakeResponse(200, {"dataPoints": []}),
    )
    client = gh.GoogleHealthClient()
    assert client.request("GET", "/users/me/dataTypes") == {"dataPoints": []}


def test_request_retries_once_after_401(monkeypatch):
    tokens = iter([
        {"access_token": "old", "base_url": "https://health.googleapis.com/v4"},
        {"access_token": "new", "base_url": "https://health.googleapis.com/v4"},
    ])
    monkeypatch.setattr(
        gh, "resolve_google_health_runtime_credentials",
        lambda **k: next(tokens),
    )
    seen = []

    def fake_request(method, url, headers=None, params=None, json=None, timeout=None):
        seen.append(headers["Authorization"])
        if len(seen) == 1:
            return _FakeResponse(401, {"error": {"message": "expired"}})
        return _FakeResponse(200, {"ok": True})

    monkeypatch.setattr(gh.httpx, "request", fake_request)
    client = gh.GoogleHealthClient()
    assert client.request("GET", "/x") == {"ok": True}
    assert seen == ["Bearer old", "Bearer new"]


def test_request_raises_auth_required_on_second_401(monkeypatch):
    monkeypatch.setattr(
        gh, "resolve_google_health_runtime_credentials",
        lambda **k: {"access_token": "tok", "base_url": "https://health.googleapis.com/v4"},
    )
    monkeypatch.setattr(
        gh.httpx, "request",
        lambda *a, **k: _FakeResponse(401, {"error": {"message": "expired"}}),
    )
    client = gh.GoogleHealthClient()
    with pytest.raises(gh.GoogleHealthAuthRequiredError):
        client.request("GET", "/x")


def test_request_raises_api_error_on_403(monkeypatch):
    monkeypatch.setattr(
        gh, "resolve_google_health_runtime_credentials",
        lambda **k: {"access_token": "tok", "base_url": "https://health.googleapis.com/v4"},
    )
    monkeypatch.setattr(
        gh.httpx, "request",
        lambda *a, **k: _FakeResponse(403, {"error": {"message": "insufficient scope"}}),
    )
    client = gh.GoogleHealthClient()
    with pytest.raises(gh.GoogleHealthAPIError) as ei:
        client.request("GET", "/x")
    assert ei.value.status_code == 403


def test_list_data_points_builds_filter(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        gh, "resolve_google_health_runtime_credentials",
        lambda **k: {"access_token": "tok", "base_url": "https://health.googleapis.com/v4"},
    )

    def fake_request(method, url, headers=None, params=None, json=None, timeout=None):
        captured.update(method=method, url=url, params=params)
        return _FakeResponse(200, {"dataPoints": [], "nextPageToken": None})

    monkeypatch.setattr(gh.httpx, "request", fake_request)
    client = gh.GoogleHealthClient()
    result = client.list_data_points(
        "exercise",
        start_iso="2026-05-13T00:00:00",
        end_iso="2026-05-13T23:59:59",
    )
    assert captured["method"] == "GET"
    assert captured["url"].endswith("/users/me/dataTypes/exercise/dataPoints")
    assert "exercise.interval.civil_start_time" in captured["params"]["filter"]
    assert "2026-05-13T00:00:00" in captured["params"]["filter"]
    assert result == {"dataPoints": [], "nextPageToken": None}


def test_list_authorized_data_types(monkeypatch):
    monkeypatch.setattr(
        gh, "resolve_google_health_runtime_credentials",
        lambda **k: {"access_token": "tok", "base_url": "https://health.googleapis.com/v4"},
    )
    monkeypatch.setattr(
        gh.httpx, "request",
        lambda *a, **k: _FakeResponse(200, {"dataTypes": [{"name": "exercise"}, {"name": "sleep"}]}),
    )
    client = gh.GoogleHealthClient()
    assert client.list_authorized_data_types() == {"dataTypes": [{"name": "exercise"}, {"name": "sleep"}]}


def test_write_data_point_posts_payload(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        gh, "resolve_google_health_runtime_credentials",
        lambda **k: {"access_token": "tok", "base_url": "https://health.googleapis.com/v4"},
    )

    def fake_request(method, url, headers=None, params=None, json=None, timeout=None):
        captured.update(method=method, url=url, body=json)
        return _FakeResponse(200, {"name": "datapoints/abc", "updateTime": "2026-05-13T00:00:00Z"})

    monkeypatch.setattr(gh.httpx, "request", fake_request)
    client = gh.GoogleHealthClient()
    result = client.write_data_point("weight", {"weight": {"weightKg": 78.2}})
    assert captured["method"] == "POST"
    assert captured["url"].endswith("/users/me/dataTypes/weight/dataPoints")
    assert captured["body"] == {"weight": {"weightKg": 78.2}}
    assert result["name"] == "datapoints/abc"
