# Google Health Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `plugins/google_health/` — a backend plugin that exposes 5 agent tools backed by Google's new Health Platform API (`health.googleapis.com/v4`), with PKCE OAuth auth registered as `hermes auth google-health`.

**Architecture:** Mirror `plugins/spotify/` exactly. Thin `GoogleHealthClient` wraps `httpx` with `Authorization: Bearer` headers and automatic refresh-on-401. Five tool handlers in `tools.py` are gated by `_check_google_health_available()`. New auth provider in `hermes_cli/auth.py` persists tokens to `~/.hermes/auth.json` under `providers.google_health`.

**Tech Stack:** Python 3.11, `httpx` (sync), `pytest` + `monkeypatch`, existing Hermes plugin loader, Google OAuth 2.0 with PKCE.

**Spec:** [`docs/superpowers/specs/2026-05-14-google-health-plugin-design.md`](../specs/2026-05-14-google-health-plugin-design.md)

**Reference plugin (read before each task):** `plugins/spotify/` — `client.py`, `tools.py`, `__init__.py`, `plugin.yaml`. Tests: `tests/tools/test_spotify_client.py`, `tests/hermes_cli/test_spotify_auth.py`. Auth glue: `hermes_cli/auth.py` (search for `spotify`) and `hermes_cli/auth_commands.py`.

---

## File Map

**Create:**
- `plugins/google_health/__init__.py` — `register(ctx)` wires 5 tools
- `plugins/google_health/plugin.yaml` — manifest, `kind: backend`
- `plugins/google_health/client.py` — `GoogleHealthClient` + error classes
- `plugins/google_health/tools.py` — 5 schemas, 5 handlers, `_check_google_health_available()`
- `plugins/google_health/README.md` — short pointer doc
- `plugins/google_health/SKILL.md` — agent guidance (when to call each tool)
- `tests/plugins/test_google_health_client.py`
- `tests/plugins/test_google_health_tools.py`
- `tests/plugins/test_google_health_register.py`
- `tests/hermes_cli/test_google_health_auth.py`
- `docs/user-guide/features/google-health.md`

**Modify:**
- `hermes_cli/auth.py` — add Google Health constants, `resolve_google_health_runtime_credentials()`, display-name + config-hint entries, logout handler
- `hermes_cli/auth_commands.py` — register `google-health` subcommand with `--write` flag; add to `_get_custom_provider_names()` if appropriate

---

## Task 1: Scaffold plugin and confirm auto-load

**Files:**
- Create: `plugins/google_health/__init__.py`
- Create: `plugins/google_health/plugin.yaml`

- [ ] **Step 1: Read the reference**

Read `plugins/spotify/plugin.yaml` and `plugins/spotify/__init__.py` to confirm the manifest shape and the `register(ctx)` signature.

- [ ] **Step 2: Write `plugin.yaml`**

```yaml
name: google_health
version: 0.1.0
description: "Google Health API integration — 5 tools (data query, data types list, daily summary, recent activity, write data point) using health.googleapis.com/v4 + PKCE Google OAuth. Auth via `hermes auth google-health`. Tools gate on `providers.google_health` in ~/.hermes/auth.json."
author: NousResearch
kind: backend
provides_tools:
  - health_data_query
  - health_data_types
  - health_daily_summary
  - health_recent_activity
  - health_write_datapoint
```

- [ ] **Step 3: Write a stub `__init__.py`**

```python
"""Google Health Platform API integration plugin — bundled, auto-loaded.

Mirrors the spotify plugin: PKCE OAuth via `hermes auth google-health`,
5 tools gated on stored credentials, runtime check prevents dispatch
when the user has not authenticated.
"""

from __future__ import annotations


def register(ctx) -> None:
    """Register Google Health tools. Filled in by later tasks."""
    return None
```

- [ ] **Step 4: Verify plugin loader discovers it**

Run: `python -c "from plugins.google_health import register; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add plugins/google_health/__init__.py plugins/google_health/plugin.yaml
git commit -m "feat(google_health): scaffold plugin manifest and registry hook"
```

---

## Task 2: Client error classes (TDD)

**Files:**
- Create: `plugins/google_health/client.py`
- Test: `tests/plugins/test_google_health_client.py`

- [ ] **Step 1: Write failing test for error class hierarchy**

```python
# tests/plugins/test_google_health_client.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/plugins/test_google_health_client.py::test_error_hierarchy -v`
Expected: FAIL (`ImportError` or `AttributeError`)

- [ ] **Step 3: Implement error classes**

```python
# plugins/google_health/client.py
"""Thin Google Health Platform API helper used by Hermes native tools."""

from __future__ import annotations

from typing import Optional


class GoogleHealthError(RuntimeError):
    """Base Google Health tool error."""


class GoogleHealthAuthRequiredError(GoogleHealthError):
    """Raised when the user needs to authenticate with Google Health first."""


class GoogleHealthAPIError(GoogleHealthError):
    """Structured Google Health API failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.path: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/plugins/test_google_health_client.py::test_error_hierarchy -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/google_health/client.py tests/plugins/test_google_health_client.py
git commit -m "feat(google_health): client error class hierarchy"
```

---

## Task 3: `GoogleHealthClient.__init__` resolves credentials

**Files:**
- Modify: `plugins/google_health/client.py`
- Test: `tests/plugins/test_google_health_client.py`

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/plugins/test_google_health_client.py -v`
Expected: FAIL (`AttributeError: resolve_google_health_runtime_credentials`)

- [ ] **Step 3: Add a temporary shim so the client can import**

Add to `plugins/google_health/client.py` near the top, BEFORE the client class:

```python
import httpx

# NOTE: real implementation lives in hermes_cli.auth (added in Task 12).
# Until then we re-export a placeholder so tests can monkeypatch.
try:
    from hermes_cli.auth import (
        AuthError,
        resolve_google_health_runtime_credentials,
    )
except ImportError:  # pragma: no cover — pre-Task-12 fallback
    class AuthError(RuntimeError):
        pass

    def resolve_google_health_runtime_credentials(**_kwargs):
        raise AuthError("Google Health auth not yet wired (Task 12 pending)")
```

Append the client skeleton:

```python
from typing import Any, Dict


class GoogleHealthClient:
    def __init__(self) -> None:
        self._runtime = self._resolve_runtime(refresh_if_expiring=True)

    def _resolve_runtime(self, *, force_refresh: bool = False, refresh_if_expiring: bool = True) -> Dict[str, Any]:
        try:
            return resolve_google_health_runtime_credentials(
                force_refresh=force_refresh,
                refresh_if_expiring=refresh_if_expiring,
            )
        except AuthError as exc:
            raise GoogleHealthAuthRequiredError(str(exc)) from exc

    @property
    def base_url(self) -> str:
        return str(self._runtime.get("base_url") or "").rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self._runtime['access_token']}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/plugins/test_google_health_client.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add plugins/google_health/client.py tests/plugins/test_google_health_client.py
git commit -m "feat(google_health): client constructor + credential resolution"
```

---

## Task 4: `GoogleHealthClient.request()` with 401-refresh-retry

**Files:**
- Modify: `plugins/google_health/client.py`
- Test: `tests/plugins/test_google_health_client.py`

- [ ] **Step 1: Add test fakes (copy the FakeResponse pattern from spotify)**

Read `tests/tools/test_spotify_client.py` — copy the `_FakeResponse` class shape into the google_health test file (top of file, after imports).

```python
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
```

- [ ] **Step 2: Write failing tests for `request()` behaviour**

```python
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
```

- [ ] **Step 3: Run tests — expect failure**

Run: `pytest tests/plugins/test_google_health_client.py -v`
Expected: FAIL (`request` not implemented)

- [ ] **Step 4: Implement `request()`**

Add to `GoogleHealthClient`:

```python
    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        allow_retry_on_401: bool = True,
        empty_response: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        response = httpx.request(
            method,
            url,
            headers=self._headers(),
            params=_strip_none(params),
            json=_strip_none(json_body) if json_body is not None else None,
            timeout=30.0,
        )
        if response.status_code == 401 and allow_retry_on_401:
            self._runtime = self._resolve_runtime(force_refresh=True, refresh_if_expiring=False)
            return self.request(
                method, path,
                params=params, json_body=json_body,
                allow_retry_on_401=False,
                empty_response=empty_response,
            )
        if response.status_code == 401:
            raise GoogleHealthAuthRequiredError(
                "Google Health authentication failed or expired."
            )
        if 200 <= response.status_code < 300:
            if not response.content:
                return empty_response or {}
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text}
        # Map error
        body = response.text[:500] if response.text else ""
        try:
            parsed = response.json()
            message = parsed.get("error", {}).get("message") or body or "Google Health API error"
        except ValueError:
            message = body or f"Google Health API error ({response.status_code})"
        err = GoogleHealthAPIError(
            message,
            status_code=response.status_code,
            response_body=body,
        )
        err.path = path
        raise err


def _strip_none(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if d is None:
        return None
    return {k: v for k, v in d.items() if v is not None}
```

- [ ] **Step 5: Run tests — expect pass**

Run: `pytest tests/plugins/test_google_health_client.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add plugins/google_health/client.py tests/plugins/test_google_health_client.py
git commit -m "feat(google_health): request() with 401-refresh-retry"
```

---

## Task 5: Client convenience methods

**Files:**
- Modify: `plugins/google_health/client.py`
- Test: `tests/plugins/test_google_health_client.py`

- [ ] **Step 1: Write failing tests for each convenience method**

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/plugins/test_google_health_client.py -v`
Expected: FAIL (methods missing)

- [ ] **Step 3: Implement convenience methods**

Append to `GoogleHealthClient`:

```python
    def list_data_points(
        self,
        data_type: str,
        *,
        start_iso: str,
        end_iso: str,
        page_token: Optional[str] = None,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        # NOTE: filter grammar verified against codelab; AND-join syntax may need adjustment.
        filter_expr = (
            f'{data_type}.interval.civil_start_time >= "{start_iso}" '
            f'AND {data_type}.interval.civil_start_time <= "{end_iso}"'
        )
        return self.request(
            "GET",
            f"/users/me/dataTypes/{data_type}/dataPoints",
            params={
                "filter": filter_expr,
                "pageToken": page_token,
                "pageSize": page_size,
            },
        )

    def list_authorized_data_types(self) -> Dict[str, Any]:
        return self.request("GET", "/users/me/dataTypes")

    def write_data_point(self, data_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.request(
            "POST",
            f"/users/me/dataTypes/{data_type}/dataPoints",
            json_body=payload,
        )
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/plugins/test_google_health_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/google_health/client.py tests/plugins/test_google_health_client.py
git commit -m "feat(google_health): client convenience methods (list/write data points)"
```

---

## Task 6: `_check_google_health_available()` and tool schemas

**Files:**
- Create: `plugins/google_health/tools.py`
- Test: `tests/plugins/test_google_health_tools.py`

- [ ] **Step 1: Read reference**

Read `plugins/spotify/tools.py` — specifically `_check_spotify_available()` (around the top), one schema example, and one handler.

- [ ] **Step 2: Write failing tests**

```python
# tests/plugins/test_google_health_tools.py
from __future__ import annotations

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
```

- [ ] **Step 3: Run tests — expect failure**

Run: `pytest tests/plugins/test_google_health_tools.py -v`
Expected: FAIL

- [ ] **Step 4: Implement `tools.py` skeleton with schemas**

```python
# plugins/google_health/tools.py
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
    store = _load_auth_store()
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
```

- [ ] **Step 5: Run tests — expect pass**

Run: `pytest tests/plugins/test_google_health_tools.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add plugins/google_health/tools.py tests/plugins/test_google_health_tools.py
git commit -m "feat(google_health): tool schemas and auth gate"
```

---

## Task 7: `health_data_query` handler

**Files:**
- Modify: `plugins/google_health/tools.py`
- Test: `tests/plugins/test_google_health_tools.py`

- [ ] **Step 1: Write failing test**

```python
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
```

Add `import json` at the top of the test file if missing.

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/plugins/test_google_health_tools.py -v`
Expected: FAIL

- [ ] **Step 3: Implement handler**

Append to `plugins/google_health/tools.py`:

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/plugins/test_google_health_tools.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add plugins/google_health/tools.py tests/plugins/test_google_health_tools.py
git commit -m "feat(google_health): health_data_query handler"
```

---

## Task 8: `health_data_types` handler

**Files:**
- Modify: `plugins/google_health/tools.py`
- Test: `tests/plugins/test_google_health_tools.py`

- [ ] **Step 1: Write failing test**

```python
def test_health_data_types_returns_simplified_list(monkeypatch):
    class S:
        def list_authorized_data_types(self):
            return {"dataTypes": [{"name": "exercise"}, {"name": "sleep"}, {"name": "heart_rate"}]}
    monkeypatch.setattr(gh_tools, "GoogleHealthClient", lambda: S())
    out = gh_tools._handle_health_data_types({})
    parsed = json.loads(out)
    assert parsed["data_types"] == ["exercise", "sleep", "heart_rate"]
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/plugins/test_google_health_tools.py::test_health_data_types_returns_simplified_list -v`

- [ ] **Step 3: Implement handler**

```python
def _handle_health_data_types(args: Dict[str, Any]) -> str:
    try:
        client = GoogleHealthClient()
        raw = client.list_authorized_data_types()
    except GoogleHealthError as exc:
        return _format_error(exc)
    names = [dt.get("name") for dt in (raw.get("dataTypes") or []) if dt.get("name")]
    return json.dumps({"data_types": names}, indent=2)
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add plugins/google_health/tools.py tests/plugins/test_google_health_tools.py
git commit -m "feat(google_health): health_data_types handler"
```

---

## Task 9: `health_recent_activity` handler

**Files:**
- Modify: `plugins/google_health/tools.py`
- Test: `tests/plugins/test_google_health_tools.py`

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement handler**

```python
import datetime as _dt


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
    try:
        if isinstance(value, str) and "." in value:
            return float(value)
        return int(value)
    except (TypeError, ValueError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def _handle_health_recent_activity(args: Dict[str, Any]) -> str:
    limit = int(args.get("limit") or 5)
    limit = max(1, min(limit, 50))
    # Use a wide window — last 30 days — and let the API sort/limit.
    now = _dt.datetime.utcnow()
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
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add plugins/google_health/tools.py tests/plugins/test_google_health_tools.py
git commit -m "feat(google_health): health_recent_activity handler"
```

---

## Task 10: `health_daily_summary` handler

**Files:**
- Modify: `plugins/google_health/tools.py`
- Test: `tests/plugins/test_google_health_tools.py`

- [ ] **Step 1: Write failing test**

```python
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

    class S:
        list_data_points = staticmethod(list_data_points)

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
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement handler**

```python
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
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add plugins/google_health/tools.py tests/plugins/test_google_health_tools.py
git commit -m "feat(google_health): health_daily_summary handler with multi-type aggregation"
```

---

## Task 11: `health_write_datapoint` handler

**Files:**
- Modify: `plugins/google_health/tools.py`
- Test: `tests/plugins/test_google_health_tools.py`

- [ ] **Step 1: Write failing tests**

```python
def test_health_write_datapoint_happy_path(monkeypatch):
    class S:
        def __init__(self): self.called = None
        def write_data_point(self, dt, payload):
            self.called = (dt, payload)
            return {"name": "datapoints/abc", "updateTime": "2026-05-13T00:00:00Z"}
    s = S()
    monkeypatch.setattr(gh_tools, "GoogleHealthClient", lambda: s)
    out = gh_tools._handle_health_write_datapoint({
        "data_type": "weight",
        "payload": {"weight": {"weightKg": 78.2}},
    })
    parsed = json.loads(out)
    assert parsed["name"] == "datapoints/abc"
    assert s.called == ("weight", {"weight": {"weightKg": 78.2}})


def test_health_write_datapoint_scope_error(monkeypatch):
    from plugins.google_health.client import GoogleHealthAPIError
    class S:
        def write_data_point(self, dt, payload):
            raise GoogleHealthAPIError("scope", status_code=403, response_body="")
    monkeypatch.setattr(gh_tools, "GoogleHealthClient", lambda: S())
    out = gh_tools._handle_health_write_datapoint({"data_type": "weight", "payload": {}})
    assert "--write" in out
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add plugins/google_health/tools.py tests/plugins/test_google_health_tools.py
git commit -m "feat(google_health): health_write_datapoint handler"
```

---

## Task 12: Auth provider in `hermes_cli/auth.py`

**Files:**
- Modify: `hermes_cli/auth.py`
- Test: `tests/hermes_cli/test_google_health_auth.py`

- [ ] **Step 1: Read reference**

Read `hermes_cli/auth.py` sections matching `spotify` — specifically `DEFAULT_SPOTIFY_*` constants, `resolve_spotify_runtime_credentials`, `_store_provider_state` callers, display-name map, config-hint map, and the logout code path.

- [ ] **Step 2: Write failing test**

```python
# tests/hermes_cli/test_google_health_auth.py
from __future__ import annotations

import pytest
from hermes_cli import auth as auth_mod


def test_resolve_google_health_runtime_credentials_returns_token(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    with auth_mod._auth_store_lock():
        store = auth_mod._load_auth_store()
        auth_mod._store_provider_state(
            store,
            "google_health",
            {
                "client_id": "gh-client",
                "redirect_uri": "http://127.0.0.1:43828/google-health/callback",
                "api_base_url": auth_mod.DEFAULT_GOOGLE_HEALTH_API_BASE_URL,
                "auth_endpoint": auth_mod.DEFAULT_GOOGLE_HEALTH_AUTH_ENDPOINT,
                "token_endpoint": auth_mod.DEFAULT_GOOGLE_HEALTH_TOKEN_ENDPOINT,
                "access_token": "live-token",
                "refresh_token": "refresh-token",
                "expires_at": 9999999999,
                "scope": "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly",
            },
            set_active=False,
        )
        auth_mod._save_auth_store(store)

    runtime = auth_mod.resolve_google_health_runtime_credentials(refresh_if_expiring=False)
    assert runtime["access_token"] == "live-token"
    assert runtime["base_url"] == auth_mod.DEFAULT_GOOGLE_HEALTH_API_BASE_URL
```

- [ ] **Step 3: Run — expect FAIL**

Run: `pytest tests/hermes_cli/test_google_health_auth.py -v`
Expected: FAIL (`AttributeError: DEFAULT_GOOGLE_HEALTH_API_BASE_URL`)

- [ ] **Step 4: Add constants and resolver to `hermes_cli/auth.py`**

Locate the block of `DEFAULT_SPOTIFY_*` constants near the top of `hermes_cli/auth.py` and add a parallel block. Then locate `resolve_spotify_runtime_credentials` and add a parallel function below it.

Constants block:

```python
DEFAULT_GOOGLE_HEALTH_API_BASE_URL = "https://health.googleapis.com/v4"
DEFAULT_GOOGLE_HEALTH_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
DEFAULT_GOOGLE_HEALTH_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DEFAULT_GOOGLE_HEALTH_SCOPE_READ = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly"
DEFAULT_GOOGLE_HEALTH_SCOPE_WRITE = "https://www.googleapis.com/auth/googlehealth.activity_and_fitness"
```

Resolver:

```python
def resolve_google_health_runtime_credentials(
    *,
    force_refresh: bool = False,
    refresh_if_expiring: bool = True,
) -> dict:
    """Return a runtime credential dict for the Google Health provider.

    Mirrors resolve_spotify_runtime_credentials: returns
    {access_token, base_url, scope, ...}. Refreshes on expiry using the
    stored refresh_token against the Google token endpoint.
    """
    with _auth_store_lock():
        store = _load_auth_store()
        provider = (store.get("providers") or {}).get("google_health")
        if not provider:
            raise AuthError("Google Health is not authenticated. Run `hermes auth google-health`.")

        if force_refresh or (refresh_if_expiring and _provider_token_expiring(provider)):
            provider = _refresh_google_health_token(provider)
            _store_provider_state(store, "google_health", provider, set_active=False)
            _save_auth_store(store)

        return {
            "access_token": provider["access_token"],
            "base_url": provider.get("api_base_url") or DEFAULT_GOOGLE_HEALTH_API_BASE_URL,
            "scope": provider.get("scope") or "",
        }


def _refresh_google_health_token(provider: dict) -> dict:
    """POST to the Google token endpoint with the refresh_token. Returns updated provider dict."""
    import time
    import httpx

    refresh_token = provider.get("refresh_token")
    client_id = provider.get("client_id")
    if not refresh_token or not client_id:
        raise AuthError("Google Health refresh token or client_id missing — re-run `hermes auth google-health`.")
    token_url = provider.get("token_endpoint") or DEFAULT_GOOGLE_HEALTH_TOKEN_ENDPOINT
    resp = httpx.post(
        token_url,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
        timeout=30.0,
    )
    if resp.status_code != 200:
        raise AuthError(f"Google Health token refresh failed ({resp.status_code}): {resp.text[:200]}")
    body = resp.json()
    provider = dict(provider)
    provider["access_token"] = body["access_token"]
    expires_in = int(body.get("expires_in") or 3599)
    provider["expires_at"] = int(time.time()) + expires_in - 30
    if body.get("refresh_token"):
        provider["refresh_token"] = body["refresh_token"]
    return provider
```

NOTE: if `_provider_token_expiring` does not exist with that name, use whatever helper Spotify uses (e.g. `_token_is_expiring` — search for "expires_at" in auth.py to find the canonical helper, and reuse it).

- [ ] **Step 5: Run — expect PASS**

Run: `pytest tests/hermes_cli/test_google_health_auth.py -v`
Expected: PASS

- [ ] **Step 6: Add display-name + config-hint entries**

Find `get_auth_provider_display_name` (used at line ~5435 of auth.py per grep) and add a `google_health` → `"Google Health"` mapping.

Find `_get_config_hint_for_unknown_provider` (line ~1319) and add a `google_health` hint pointing to `hermes auth google-health`.

- [ ] **Step 7: Commit**

```bash
git add hermes_cli/auth.py tests/hermes_cli/test_google_health_auth.py
git commit -m "feat(google_health): auth provider resolver + token refresh"
```

---

## Task 13: `hermes auth google-health` CLI subcommand

**Files:**
- Modify: `hermes_cli/auth_commands.py`

- [ ] **Step 1: Read reference**

Read `hermes_cli/auth_commands.py` end-to-end to understand the dispatch table, then locate the Spotify subcommand implementation (search for `spotify` in the file). The PKCE flow helper is reusable across providers.

- [ ] **Step 2: Wire `google-health` subcommand**

Add a function `_run_google_health_auth(args)` modelled on `_run_spotify_auth`:
- Start a local loopback HTTP server on a random port for the OAuth callback.
- Generate a PKCE code verifier + S256 challenge.
- Open the browser to `DEFAULT_GOOGLE_HEALTH_AUTH_ENDPOINT` with:
  - `client_id=<from config>` (read via `_read_client_id_from_config("google_health")` — search the file for how Spotify reads its client_id; reuse the same accessor or copy and rename).
  - `redirect_uri=http://127.0.0.1:<port>/google-health/callback`
  - `response_type=code`
  - `access_type=offline`
  - `prompt=consent`
  - `scope=` either `DEFAULT_GOOGLE_HEALTH_SCOPE_READ` or `DEFAULT_GOOGLE_HEALTH_SCOPE_WRITE` depending on `--write` flag (write scope is a superset).
  - `code_challenge=<S256>`, `code_challenge_method=S256`
- After the callback, POST to `DEFAULT_GOOGLE_HEALTH_TOKEN_ENDPOINT` with:
  - `grant_type=authorization_code`, `code`, `redirect_uri`, `client_id`, `code_verifier`
- Store the resulting tokens via `_store_provider_state(store, "google_health", {...}, set_active=False)`.

Register in the subcommand dispatch table next to the `spotify` entry. Add `--write` flag.

- [ ] **Step 3: Smoke-test the CLI surface (no real OAuth)**

Run: `python -m hermes_cli.main auth google-health --help`
Expected: usage text including `--write`.

Run: `python -m hermes_cli.main auth --help`
Expected: `google-health` listed.

- [ ] **Step 4: Commit**

```bash
git add hermes_cli/auth_commands.py
git commit -m "feat(google_health): hermes auth google-health subcommand (PKCE)"
```

---

## Task 14: Wire `register()` for all 5 tools

**Files:**
- Modify: `plugins/google_health/__init__.py`
- Test: `tests/plugins/test_google_health_register.py`

- [ ] **Step 1: Write failing test**

```python
# tests/plugins/test_google_health_register.py
from __future__ import annotations

from plugins.google_health import register


class _Ctx:
    def __init__(self):
        self.registered = []
    def register_tool(self, *, name, toolset, schema, handler, check_fn, emoji):
        self.registered.append((name, toolset, emoji))


def test_register_wires_five_tools():
    ctx = _Ctx()
    register(ctx)
    names = [n for n, _, _ in ctx.registered]
    assert names == [
        "health_data_query",
        "health_data_types",
        "health_daily_summary",
        "health_recent_activity",
        "health_write_datapoint",
    ]
    assert {ts for _, ts, _ in ctx.registered} == {"google_health"}
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Replace `__init__.py` stub with full implementation**

```python
"""Google Health integration plugin — bundled, auto-loaded.

Registers 5 tools (data_query, data_types, daily_summary, recent_activity,
write_datapoint) into the ``google_health`` toolset. Each tool's handler
is gated by ``_check_google_health_available()`` — when the user has not
run ``hermes auth google-health``, the tools remain registered (so they
appear in ``hermes tools``) but the runtime check prevents dispatch.
"""

from __future__ import annotations

from plugins.google_health.tools import (
    HEALTH_DAILY_SUMMARY_SCHEMA,
    HEALTH_DATA_QUERY_SCHEMA,
    HEALTH_DATA_TYPES_SCHEMA,
    HEALTH_RECENT_ACTIVITY_SCHEMA,
    HEALTH_WRITE_DATAPOINT_SCHEMA,
    _check_google_health_available,
    _handle_health_daily_summary,
    _handle_health_data_query,
    _handle_health_data_types,
    _handle_health_recent_activity,
    _handle_health_write_datapoint,
)

_TOOLS = (
    ("health_data_query",      HEALTH_DATA_QUERY_SCHEMA,      _handle_health_data_query,      "🏃"),
    ("health_data_types",      HEALTH_DATA_TYPES_SCHEMA,      _handle_health_data_types,      "📋"),
    ("health_daily_summary",   HEALTH_DAILY_SUMMARY_SCHEMA,   _handle_health_daily_summary,   "🌅"),
    ("health_recent_activity", HEALTH_RECENT_ACTIVITY_SCHEMA, _handle_health_recent_activity, "🏋️"),
    ("health_write_datapoint", HEALTH_WRITE_DATAPOINT_SCHEMA, _handle_health_write_datapoint, "✍️"),
)


def register(ctx) -> None:
    """Register all Google Health tools. Called once by the plugin loader."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="google_health",
            schema=schema,
            handler=handler,
            check_fn=_check_google_health_available,
            emoji=emoji,
        )
```

- [ ] **Step 4: Run — expect PASS**

- [ ] **Step 5: Run full plugin test suite**

Run: `pytest tests/plugins/test_google_health_client.py tests/plugins/test_google_health_tools.py tests/plugins/test_google_health_register.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add plugins/google_health/__init__.py tests/plugins/test_google_health_register.py
git commit -m "feat(google_health): wire register() for all 5 tools"
```

---

## Task 15: User docs

**Files:**
- Create: `docs/user-guide/features/google-health.md`
- Create: `plugins/google_health/README.md`
- Create: `plugins/google_health/SKILL.md`

- [ ] **Step 1: Read reference**

Read whichever Spotify doc exists at `docs/user-guide/features/spotify.md` (or the equivalent) to match tone and section headers.

- [ ] **Step 2: Write `plugins/google_health/README.md`**

```markdown
# Google Health Plugin

Native integration with Google's Health Platform API
(`health.googleapis.com/v4`) — the API that ships with Fitbit Air and
future Google health hardware.

**Setup:** `hermes auth google-health` (add `--write` if you want
the agent to log manual entries like weight or sleep notes).

**Tools added:** `health_data_query`, `health_data_types`,
`health_daily_summary`, `health_recent_activity`, `health_write_datapoint`.

See [docs/user-guide/features/google-health.md](../../docs/user-guide/features/google-health.md) for full setup.
```

- [ ] **Step 3: Write `docs/user-guide/features/google-health.md`**

Full setup walkthrough: (1) create a Google Cloud project, (2) enable the Health API, (3) configure OAuth consent screen, (4) create an OAuth client (type: Desktop app), (5) `hermes config set google_health.client_id <id>`, (6) `hermes auth google-health`. Then a tool reference table with one row per tool. Then a troubleshooting section covering "Google Health authentication failed or expired", "scope insufficient", and rate limits.

(The text should be 150–300 words plus the table — keep it operational, not marketing copy.)

- [ ] **Step 4: Write `plugins/google_health/SKILL.md`**

Agent guidance: when to call each tool, common user phrasings ("how did I sleep last night" → `health_daily_summary` with yesterday's date; "what was my run this morning" → `health_recent_activity` then narrate; "log that I weigh 78kg" → `health_write_datapoint` with `data_type=weight`). 100–200 words.

- [ ] **Step 5: Commit**

```bash
git add plugins/google_health/README.md plugins/google_health/SKILL.md docs/user-guide/features/google-health.md
git commit -m "docs(google_health): user setup, tool reference, agent skill guide"
```

---

## Task 16: Full test sweep + plugin auto-load smoke check

- [ ] **Step 1: Run the full plugin test set**

Run: `pytest tests/plugins/test_google_health_client.py tests/plugins/test_google_health_tools.py tests/plugins/test_google_health_register.py tests/hermes_cli/test_google_health_auth.py -v`
Expected: PASS (all)

- [ ] **Step 2: Run the broader test suite to catch regressions**

Run: `scripts/run_tests.sh` (or `pytest -x` if on Windows where the shell script doesn't run)
Expected: PASS

- [ ] **Step 3: Verify the plugin auto-loads**

Run: `python -m hermes_cli.main tools 2>&1 | grep -iE "google_health|health_data_query"`
Expected: tools listed in the `google_health` toolset.

- [ ] **Step 4: Verify the auth subcommand surface**

Run: `python -m hermes_cli.main auth google-health --help`
Expected: usage text including `--write`.

- [ ] **Step 5: Final commit (if anything was tweaked)**

```bash
git status
# if clean, nothing to commit; otherwise:
git commit -am "chore(google_health): post-sweep fixups"
```

---

## Verify-at-implementation-time items (from spec)

The following items in the spec are flagged as "confirm against live API" — when actually running OAuth and hitting the API, the implementer should:

1. **Filter grammar** — Task 5 uses `<dt>.interval.civil_start_time >= "X" AND <dt>.interval.civil_start_time <= "Y"`. If the API rejects the `AND` form, switch to two separate filter expressions or whatever syntax the live API returns helpful errors for.
2. **Pagination param name** — Task 5 sends `pageToken` and `pageSize`. If the API uses `page_token` / `page_size` (snake_case), swap them; the existing test will continue to pass because it asserts on the value being present, not the key (re-read the test if the key name is asserted there).
3. **Server-side daily summary** — Task 10 fans out client-side. If a daily-summary endpoint exists, replace the body of `_handle_health_daily_summary` with a single call.
4. **DataType identifiers** — `sleep`, `heart_rate`, `spo2` are inferred. Confirm during smoke-test in Task 16; if the API uses different identifiers, fix `_handle_health_daily_summary`'s fan-out list.
5. **Write payload shape** — Task 11 passes payload through. Once a real write succeeds, document the canonical shape per dataType in `docs/user-guide/features/google-health.md`.

---

## Spec coverage map

| Spec section | Implemented in task |
| --- | --- |
| Plugin scaffold + auto-load | Task 1 |
| Client error classes | Task 2 |
| Client constructor + credential resolution | Task 3 |
| `request()` with 401 refresh retry | Task 4 |
| `list_data_points` / `list_authorized_data_types` / `write_data_point` | Task 5 |
| Tool schemas + auth gate | Task 6 |
| `health_data_query` | Task 7 |
| `health_data_types` | Task 8 |
| `health_recent_activity` | Task 9 |
| `health_daily_summary` | Task 10 |
| `health_write_datapoint` | Task 11 |
| Auth provider + token refresh | Task 12 |
| `hermes auth google-health` CLI | Task 13 |
| `register()` for all 5 tools | Task 14 |
| User docs + agent SKILL.md | Task 15 |
| Regression sweep + smoke checks | Task 16 |
