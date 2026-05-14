"""Google Health tool schemas + handlers.

Each handler instantiates a fresh `GoogleHealthClient` so token refresh
state stays per-call. Handlers translate `GoogleHealth*Error` exceptions
into agent-facing strings; they never raise out of the tool boundary.
"""

from __future__ import annotations

import datetime as _dt
import json
from typing import Any, Dict, Tuple

from plugins.google_health.client import (
    GoogleHealthAPIError,
    GoogleHealthAuthRequiredError,
    GoogleHealthClient,
    GoogleHealthError,
)


def _check_google_health_available() -> Tuple[bool, str]:
    """Return (is_available, message). Called by the toolset gate."""
    try:
        from hermes_cli.auth import _load_auth_store  # type: ignore
    except ImportError:
        return False, "Run `hermes auth google-health` to enable Google Health tools."
    try:
        store = _load_auth_store()
    except Exception:
        return False, "Run `hermes auth google-health` to enable Google Health tools."
    providers = store.get("providers") or {}
    if "google_health" not in providers:
        return False, "Run `hermes auth google-health` to enable Google Health tools."
    return True, ""


_AUTH_REQUIRED_MSG = (
    "Google Health authentication failed or expired. "
    "Run `hermes auth google-health` again."
)
_SCOPE_INSUFFICIENT_MSG = (
    "Google Health rejected the request because the current auth scope is insufficient. "
    "Re-run `hermes auth google-health` (with `--write` if you need write access)."
)


HEALTH_DATA_QUERY_SCHEMA = {
    "name": "health_data_query",
    "description": (
        "Query Google Health Platform data points for a single dataType "
        "(e.g. 'exercise', 'sleep', 'heart_rate', 'spo2') across a time window."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "data_type": {"type": "string", "description": "Health dataType identifier."},
            "start": {"type": "string", "description": "ISO datetime, inclusive."},
            "end": {"type": "string", "description": "ISO datetime, inclusive."},
            "page_token": {"type": "string"},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 250},
        },
        "required": ["data_type", "start", "end"],
    },
}

HEALTH_DATA_TYPES_SCHEMA = {
    "name": "health_data_types",
    "description": "List which Google Health dataTypes the user has authorised.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

HEALTH_DAILY_SUMMARY_SCHEMA = {
    "name": "health_daily_summary",
    "description": "One-call summary of a single day (steps, sleep, HR, calories, SpO2).",
    "parameters": {
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "YYYY-MM-DD; defaults to yesterday."},
        },
        "required": [],
    },
}

HEALTH_RECENT_ACTIVITY_SCHEMA = {
    "name": "health_recent_activity",
    "description": "Return the user's most recent exercise sessions.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": [],
    },
}

HEALTH_WRITE_DATAPOINT_SCHEMA = {
    "name": "health_write_datapoint",
    "description": (
        "Write a manual data point. Requires the write OAuth scope "
        "(run `hermes auth google-health --write`). Payload is passed through "
        "to the API; the caller is responsible for matching the dataType schema."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "data_type": {"type": "string"},
            "payload": {"type": "object"},
        },
        "required": ["data_type", "payload"],
    },
}


def _format_error(exc: GoogleHealthError) -> str:
    if isinstance(exc, GoogleHealthAuthRequiredError):
        return _AUTH_REQUIRED_MSG
    if isinstance(exc, GoogleHealthAPIError):
        if exc.status_code == 403:
            return _SCOPE_INSUFFICIENT_MSG
        if exc.status_code == 429:
            return f"Google Health rate limit hit (429). {exc}"
        return f"Google Health API error ({exc.status_code}): {exc}"
    return f"Google Health error: {exc}"


def _handle_health_data_query(args: Dict[str, Any]) -> str:
    try:
        client = GoogleHealthClient()
        result = client.list_data_points(
            args["data_type"],
            start_iso=args["start"],
            end_iso=args["end"],
            page_token=args.get("page_token"),
            page_size=args.get("page_size"),
        )
    except GoogleHealthError as exc:
        return _format_error(exc)
    return json.dumps(result, indent=2, default=str)


def _handle_health_data_types(args: Dict[str, Any]) -> str:
    try:
        client = GoogleHealthClient()
        raw = client.list_authorized_data_types()
    except GoogleHealthError as exc:
        return _format_error(exc)
    names = [dt.get("name") for dt in (raw.get("dataTypes") or []) if dt.get("name")]
    return json.dumps({"data_types": names}, indent=2)


def _parse_duration_seconds(value) -> Any:
    if value is None:
        return None
    s = str(value)
    if s.endswith("s"):
        s = s[:-1]
    try:
        return int(float(s))
    except ValueError:
        return None


def _coerce_number(value) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return value
    try:
        s = str(value)
        if "." in s:
            return float(s)
        return int(s)
    except (TypeError, ValueError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def _handle_health_recent_activity(args: Dict[str, Any]) -> str:
    limit = int(args.get("limit") or 5)
    limit = max(1, min(limit, 50))
    now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    start = (now - _dt.timedelta(days=30)).isoformat(timespec="seconds")
    end = now.isoformat(timespec="seconds")
    try:
        client = GoogleHealthClient()
        raw = client.list_data_points(
            "exercise",
            start_iso=start,
            end_iso=end,
            page_size=limit,
        )
    except GoogleHealthError as exc:
        return _format_error(exc)

    sessions = []
    for dp in (raw.get("dataPoints") or [])[:limit]:
        ex = dp.get("exercise") or {}
        interval = ex.get("interval") or {}
        metrics = ex.get("metricsSummary") or {}
        distance_mm = _coerce_number(metrics.get("distanceMillimeters"))
        sessions.append({
            "startTime": interval.get("startTime"),
            "endTime": interval.get("endTime"),
            "exerciseType": ex.get("exerciseType"),
            "displayName": ex.get("displayName"),
            "calories_kcal": _coerce_number(metrics.get("caloriesKcal")),
            "distance_meters": (distance_mm / 1000.0) if distance_mm is not None else None,
            "steps": _coerce_number(metrics.get("steps")),
            "avg_heart_rate_bpm": _coerce_number(metrics.get("averageHeartRateBeatsPerMinute")),
            "active_duration_seconds": _parse_duration_seconds(ex.get("activeDuration")),
        })
    return json.dumps({"sessions": sessions}, indent=2, default=str)


def _yesterday_iso() -> str:
    return (_dt.date.today() - _dt.timedelta(days=1)).isoformat()


def _safe_list_data_points(client, data_type, start, end):
    try:
        return client.list_data_points(data_type, start_iso=start, end_iso=end)
    except GoogleHealthAPIError as exc:
        if exc.status_code in (403, 404):
            return {"dataPoints": []}
        raise


def _handle_health_daily_summary(args: Dict[str, Any]) -> str:
    date = args.get("date") or _yesterday_iso()
    start = f"{date}T00:00:00"
    end = f"{date}T23:59:59"

    summary: Dict[str, Any] = {
        "date": date,
        "steps": None,
        "distance_meters": None,
        "calories_kcal": None,
        "active_duration_seconds": None,
        "avg_heart_rate_bpm": None,
        "resting_heart_rate_bpm": None,
        "sleep_total_minutes": None,
        "sleep_efficiency_pct": None,
        "spo2_avg_pct": None,
    }
    try:
        client = GoogleHealthClient()

        ex = _safe_list_data_points(client, "exercise", start, end)
        steps = calories = active = distance_mm = hr_sum = hr_count = 0
        for dp in ex.get("dataPoints") or []:
            metrics = (dp.get("exercise") or {}).get("metricsSummary") or {}
            steps += _coerce_number(metrics.get("steps")) or 0
            calories += _coerce_number(metrics.get("caloriesKcal")) or 0
            distance_mm += _coerce_number(metrics.get("distanceMillimeters")) or 0
            active += _parse_duration_seconds((dp.get("exercise") or {}).get("activeDuration")) or 0
            hr = _coerce_number(metrics.get("averageHeartRateBeatsPerMinute"))
            if hr is not None:
                hr_sum += hr
                hr_count += 1
        if ex.get("dataPoints"):
            summary["steps"] = steps or None
            summary["calories_kcal"] = calories or None
            summary["distance_meters"] = (distance_mm / 1000.0) if distance_mm else None
            summary["active_duration_seconds"] = active or None
            summary["avg_heart_rate_bpm"] = (hr_sum // hr_count) if hr_count else None

        sleep = _safe_list_data_points(client, "sleep", start, end)
        if sleep.get("dataPoints"):
            s = sleep["dataPoints"][0].get("sleep") or {}
            summary["sleep_total_minutes"] = _coerce_number(s.get("sleepDurationMinutes"))
            summary["sleep_efficiency_pct"] = _coerce_number(s.get("sleepEfficiencyPct"))

        hr = _safe_list_data_points(client, "heart_rate", start, end)
        if hr.get("dataPoints"):
            h = hr["dataPoints"][0].get("heartRate") or {}
            summary["resting_heart_rate_bpm"] = _coerce_number(h.get("restingHeartRateBpm"))

        spo2 = _safe_list_data_points(client, "spo2", start, end)
        if spo2.get("dataPoints"):
            p = spo2["dataPoints"][0].get("spo2") or {}
            summary["spo2_avg_pct"] = _coerce_number(p.get("averagePct"))

    except GoogleHealthError as exc:
        return _format_error(exc)

    return json.dumps(summary, indent=2)


def _handle_health_write_datapoint(args: Dict[str, Any]) -> str:
    data_type = args.get("data_type")
    payload = args.get("payload") or {}
    if not data_type or not isinstance(payload, dict):
        return "health_write_datapoint requires `data_type` (string) and `payload` (object)."
    try:
        client = GoogleHealthClient()
        result = client.write_data_point(data_type, payload)
    except GoogleHealthError as exc:
        return _format_error(exc)
    return json.dumps(result, indent=2, default=str)
