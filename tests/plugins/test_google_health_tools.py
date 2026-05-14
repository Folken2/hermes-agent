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


def test_health_data_types_returns_simplified_list(monkeypatch):
    class S:
        def list_authorized_data_types(self):
            return {"dataTypes": [{"name": "exercise"}, {"name": "sleep"}, {"name": "heart_rate"}]}
    monkeypatch.setattr(gh_tools, "GoogleHealthClient", lambda: S())
    out = gh_tools._handle_health_data_types({})
    parsed = json.loads(out)
    assert parsed["data_types"] == ["exercise", "sleep", "heart_rate"]


def test_health_recent_activity_extracts_session_fields(monkeypatch):
    sample = {
        "dataPoints": [
            {
                "exercise": {
                    "interval": {"startTime": "2026-05-13T08:00:00Z", "endTime": "2026-05-13T08:25:00Z"},
                    "exerciseType": "WALKING",
                    "metricsSummary": {
                        "caloriesKcal": 16,
                        "steps": "2038",
                        "distanceMillimeters": 1609344,
                        "averageHeartRateBeatsPerMinute": "81",
                    },
                    "displayName": "Walk",
                    "activeDuration": "900s",
                }
            }
        ],
        "nextPageToken": None,
    }

    class S:
        def list_data_points(self, dt, *, start_iso, end_iso, page_token=None, page_size=None):
            assert dt == "exercise"
            assert page_size == 5
            return sample

    monkeypatch.setattr(gh_tools, "GoogleHealthClient", lambda: S())
    out = gh_tools._handle_health_recent_activity({"limit": 5})
    parsed = json.loads(out)
    assert len(parsed["sessions"]) == 1
    sess = parsed["sessions"][0]
    assert sess["exerciseType"] == "WALKING"
    assert sess["calories_kcal"] == 16
    assert sess["steps"] == 2038
    assert sess["distance_meters"] == pytest.approx(1609.344)
    assert sess["avg_heart_rate_bpm"] == 81
    assert sess["active_duration_seconds"] == 900


def test_health_daily_summary_aggregates_multi_type(monkeypatch):
    def list_data_points(dt, *, start_iso, end_iso, page_token=None, page_size=None):
        if dt == "exercise":
            return {"dataPoints": [{"exercise": {"metricsSummary": {
                "caloriesKcal": 100, "steps": "5000", "distanceMillimeters": 4000000,
                "averageHeartRateBeatsPerMinute": "95"}, "activeDuration": "1800s"}}]}
        if dt == "sleep":
            return {"dataPoints": [{"sleep": {"sleepDurationMinutes": 420, "sleepEfficiencyPct": 88}}]}
        if dt == "heart_rate":
            return {"dataPoints": [{"heartRate": {"restingHeartRateBpm": 58}}]}
        if dt == "spo2":
            return {"dataPoints": [{"spo2": {"averagePct": 96.5}}]}
        return {"dataPoints": []}

    _fn = list_data_points

    class S:
        list_data_points = staticmethod(_fn)

    monkeypatch.setattr(gh_tools, "GoogleHealthClient", lambda: S())
    out = gh_tools._handle_health_daily_summary({"date": "2026-05-13"})
    parsed = json.loads(out)
    assert parsed["date"] == "2026-05-13"
    assert parsed["steps"] == 5000
    assert parsed["calories_kcal"] == 100
    assert parsed["distance_meters"] == pytest.approx(4000.0)
    assert parsed["active_duration_seconds"] == 1800
    assert parsed["avg_heart_rate_bpm"] == 95
    assert parsed["resting_heart_rate_bpm"] == 58
    assert parsed["sleep_total_minutes"] == 420
    assert parsed["sleep_efficiency_pct"] == 88
    assert parsed["spo2_avg_pct"] == 96.5


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
