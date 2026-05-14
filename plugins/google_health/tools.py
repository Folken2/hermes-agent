"""Google Health tool schemas + handlers.

Each handler instantiates a fresh `GoogleHealthClient` so token refresh
state stays per-call. Handlers translate `GoogleHealth*Error` exceptions
into agent-facing strings; they never raise out of the tool boundary.
"""

from __future__ import annotations

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
