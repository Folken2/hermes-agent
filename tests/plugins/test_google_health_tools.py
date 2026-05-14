from __future__ import annotations

import json

import pytest

from plugins.google_health import tools as gh_tools


def test_check_returns_false_when_no_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    ok, msg = gh_tools._check_google_health_available()
    assert ok is False
    assert "hermes auth google-health" in msg


class _StubClient:
    def __init__(self, payload=None, raises=None):
        self.payload = payload
        self.raises = raises
        self.calls = []

    def list_data_points(self, data_type, *, start_iso, end_iso, page_token=None, page_size=None):
        if self.raises:
            raise self.raises
        self.calls.append((data_type, start_iso, end_iso, page_token, page_size))
        return self.payload


def test_health_data_query_happy_path(monkeypatch):
    stub = _StubClient(payload={"dataPoints": [{"name": "x"}], "nextPageToken": None})
    monkeypatch.setattr(gh_tools, "GoogleHealthClient", lambda: stub)
    out = gh_tools._handle_health_data_query({
        "data_type": "exercise",
        "start": "2026-05-13T00:00:00",
        "end": "2026-05-13T23:59:59",
    })
    parsed = json.loads(out) if isinstance(out, str) else out
    assert parsed["dataPoints"][0]["name"] == "x"
    assert stub.calls == [("exercise", "2026-05-13T00:00:00", "2026-05-13T23:59:59", None, None)]


def test_health_data_query_auth_required(monkeypatch):
    from plugins.google_health.client import GoogleHealthAuthRequiredError
    stub = _StubClient(raises=GoogleHealthAuthRequiredError("nope"))
    monkeypatch.setattr(gh_tools, "GoogleHealthClient", lambda: stub)
    out = gh_tools._handle_health_data_query({
        "data_type": "exercise",
        "start": "2026-05-13T00:00:00",
        "end": "2026-05-13T23:59:59",
    })
    assert "hermes auth google-health" in (out if isinstance(out, str) else json.dumps(out))


def test_schemas_all_have_name_and_description():
    for schema in [
        gh_tools.HEALTH_DATA_QUERY_SCHEMA,
        gh_tools.HEALTH_DATA_TYPES_SCHEMA,
        gh_tools.HEALTH_DAILY_SUMMARY_SCHEMA,
        gh_tools.HEALTH_RECENT_ACTIVITY_SCHEMA,
        gh_tools.HEALTH_WRITE_DATAPOINT_SCHEMA,
    ]:
        assert "name" in schema
        assert "description" in schema
        assert "parameters" in schema or "input_schema" in schema
