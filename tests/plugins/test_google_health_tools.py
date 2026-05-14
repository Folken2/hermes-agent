from __future__ import annotations

import json

import pytest

from plugins.google_health import tools as gh_tools


def test_check_returns_false_when_no_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    ok, msg = gh_tools._check_google_health_available()
    assert ok is False
    assert "hermes auth google-health" in msg


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
