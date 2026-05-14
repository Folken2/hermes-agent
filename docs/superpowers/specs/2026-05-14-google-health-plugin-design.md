# Google Health Plugin — Design Spec

**Date:** 2026-05-14
**Owner:** albert.folch
**Status:** Approved for plan-writing

## Summary

Add `plugins/google_health/` — a backend plugin that lets the Hermes agent read (and optionally write) the user's health data from the Google Health Platform API (`health.googleapis.com/v4`). This is the new API launched alongside Fitbit Air; it is distinct from the deprecated Google Fit REST API and the older Fitbit Web API.

The plugin follows the existing Spotify plugin pattern exactly: a thin httpx client, OAuth 2.0 user credentials managed by `hermes_cli/auth.py`, and a small set of agent-facing tools that gate on `_check_google_health_available()`.

## Motivation

The user wears a Google Fitbit Air strap. Google's new Health API exposes 31 data types (exercise, sleep, heart rate, SpO2, etc.) via a single REST surface authenticated with user OAuth. Wiring it into Hermes lets the agent answer questions like "how did I sleep this week" or "summarise yesterday's workout" directly from real device data, and lets cron-scheduled routines pull morning health digests.

## Non-Goals (v1)

- Webhook subscription management. The API supports webhook push notifications, but those need a public HTTPS callback. Wiring them into the Hermes gateway is a separate feature.
- Training-plan or recommendation endpoints.
- Family-shared / multi-profile reads.
- Web-UI dashboards or charts. Tools return JSON; the agent narrates.

## Architecture

### File layout (mirrors `plugins/spotify/`)

```
plugins/google_health/
  __init__.py          # register(ctx) — wires 5 tools into "google_health" toolset
  plugin.yaml          # name, version, provides_tools, kind: backend
  client.py            # GoogleHealthClient — httpx wrapper, token refresh, error mapping
  tools.py             # 5 tool schemas + handlers + _check_google_health_available()
  README.md            # short overview + auth instructions
```

### Auth flow

New provider registered in `hermes_cli/auth.py` and `hermes_cli/auth_commands.py`:

- Command: `hermes auth google-health`
- Provider key in `~/.hermes/auth.json`: `providers.google_health`
- Flow: standard Google OAuth 2.0 authorization-code with **PKCE** (no client secret stored on disk — matches Spotify pattern and is the Google-recommended flow for installed apps).
- Authorization endpoint: `https://accounts.google.com/o/oauth2/v2/auth`
- Token endpoint: `https://oauth2.googleapis.com/token`
- `access_type=offline`, `prompt=consent` (so refresh token is always issued)
- Scopes requested (read-only by default; write scope only if user passes `--write`):
  - `https://www.googleapis.com/auth/googlehealth.activity_and_fitness.readonly`
  - (write variant when opted in) `https://www.googleapis.com/auth/googlehealth.activity_and_fitness`
- User supplies their own Google Cloud OAuth client ID via `hermes config set google_health.client_id <id>` — we cannot ship a Google client ID/secret (same UX constraint as Spotify).
- Token refresh: access tokens live ~3600s; the client refreshes on 401 via the stored refresh token using `resolve_google_health_runtime_credentials(refresh_if_expiring=True)`.

### Client (`client.py`)

`GoogleHealthClient` — direct analogue of `SpotifyClient`:

- Base URL: `https://health.googleapis.com/v4`
- `_headers()` adds `Authorization: Bearer <access_token>` and `Accept: application/json`
- `request(method, path, *, params=None, json_body=None)` with 401-retry-after-refresh
- Error classes: `GoogleHealthError`, `GoogleHealthAuthRequiredError`, `GoogleHealthAPIError(status_code, response_body)`
- Convenience methods used by tools:
  - `list_data_points(data_type, *, start_iso, end_iso, page_token=None, page_size=None)` → `GET /users/me/dataTypes/{data_type}/dataPoints` with `filter` query param
  - `list_authorized_data_types()` → `GET /users/me/dataTypes`
  - `daily_summary(date_iso)` → composite call (fan-out over a fixed set of dataTypes, roll up client-side) — the API may expose a server-side summary endpoint; verify at implementation time and prefer it if present
  - `write_data_point(data_type, payload)` → `POST /users/me/dataTypes/{data_type}/dataPoints` — gated on write scope

### Tools (5)

All tools live in the `google_health` toolset. Each is gated by `_check_google_health_available()` which returns `False` (with an explanatory message) when `providers.google_health` is missing from `~/.hermes/auth.json`. Tools remain registered so they appear in `hermes tools`.

1. **`health_data_query`** — generic query for a single data type over a time window.
   - Inputs: `data_type` (string, required, e.g. `"exercise"`, `"sleep"`, `"heart_rate"`, `"spo2"`), `start` (ISO datetime), `end` (ISO datetime), `page_token` (optional), `page_size` (optional, default 50, max 250).
   - Output: `{dataPoints: [...], nextPageToken: str | null}`.
   - Builds `filter=<dataType>.interval.civil_start_time >= "<start>" AND <dataType>.interval.civil_start_time <= "<end>"` (exact filter grammar verified at implementation time against the codelab).

2. **`health_data_types`** — list which of the 31 data types the user has authorised.
   - Inputs: none.
   - Output: `{data_types: ["exercise", "sleep", ...]}`.
   - Useful for the agent to check capability before calling `health_data_query`.

3. **`health_daily_summary`** — one-call summary of a single day.
   - Inputs: `date` (YYYY-MM-DD, defaults to "yesterday").
   - Output: `{date, steps, distance_meters, calories_kcal, active_duration_seconds, avg_heart_rate_bpm, resting_heart_rate_bpm, sleep_total_minutes, sleep_efficiency_pct, spo2_avg_pct}`.
   - Implementation: prefer a server-side daily-summary endpoint if the API exposes one (codelab navigation mentions "roll up daily summaries"); fall back to fanning out `health_data_query` over a fixed dataType set and aggregating client-side. Missing fields are returned as `null`, not omitted.

4. **`health_recent_activity`** — last N exercise sessions.
   - Inputs: `limit` (int, default 5, max 50).
   - Output: `{sessions: [{startTime, endTime, exerciseType, displayName, calories_kcal, distance_meters, steps, avg_heart_rate_bpm, active_duration_seconds}, ...]}`.
   - Shape mirrors the example response in the codelab screenshot.

5. **`health_write_datapoint`** — write a manual entry. Disabled by default.
   - Inputs: `data_type` (string), `payload` (object — passed through to the API; the agent is responsible for shape).
   - Output: `{name, updateTime}` from the API response.
   - Gate: in addition to the standard auth check, returns an error if the stored auth was not granted with the write scope. Users must run `hermes auth google-health --write` to enable.

### Registration glue

- `plugin.yaml` declares `kind: backend` and `provides_tools: [health_data_query, health_data_types, health_daily_summary, health_recent_activity, health_write_datapoint]` so the plugin auto-loads.
- `__init__.py` exports a single `register(ctx)` that iterates a `_TOOLS` tuple and calls `ctx.register_tool(name=, toolset="google_health", schema=, handler=, check_fn=_check_google_health_available, emoji=)`. Emojis: `🏃 📋 🌅 🏋️ ✍️`.

### `hermes_cli` changes

- `hermes_cli/auth.py`: add `resolve_google_health_runtime_credentials()`, `_get_config_hint_for_unknown_provider` entry, display-name mapping, logout support.
- `hermes_cli/auth_commands.py`: add `google-health` subcommand with `--write` flag; register in the providers list returned by `_get_custom_provider_names()`.
- No changes to `cli.py` or `run_agent.py` are expected — the plugin loader auto-discovers `plugins/google_health/` on startup.

## Data Flow

```
agent turn
  └─> tools.health_daily_summary(date="2026-05-13")
        └─> GoogleHealthClient(resolve_google_health_runtime_credentials())
              ├─> if access_token expired → POST oauth2.googleapis.com/token (refresh)
              ├─> GET /v4/users/me/dataTypes/exercise/dataPoints?filter=...
              ├─> GET /v4/users/me/dataTypes/sleep/dataPoints?filter=...
              └─> GET /v4/users/me/dataTypes/heart_rate/dataPoints?filter=...
        └─> client-side aggregation → flat JSON summary
  └─> JSON returned to model
```

## Error Handling

- `GoogleHealthAuthRequiredError` (no token, refresh failed, revoked) → tool returns the user-facing string `"Google Health authentication failed or expired. Run `hermes auth google-health` again."` — same shape as Spotify.
- `GoogleHealthAPIError` with 403 + scope-related body → `"Google Health rejected the request because the current auth scope is insufficient. Re-run `hermes auth google-health` (with `--write` if you need write access)."`
- `429` → tool returns a short message including the `Retry-After` header value if present. No internal retry loop in v1.
- All other 4xx/5xx → tool returns `f"Google Health API error ({status_code}): {short body}"` and the agent decides what to do.

## Testing

- Unit tests under `tests/plugins/google_health/`:
  - `test_client.py` — `httpx_mock` fixtures cover happy path, 401 → refresh → retry, 401 after refresh (auth-required), 403 scope error, 429, paginated query.
  - `test_tools.py` — each tool handler invoked with a mocked client; assert schema validation, missing-auth gating, and exact output shape.
  - `test_register.py` — confirm `register()` wires all 5 tools into the `google_health` toolset.
- No integration tests against the live API in v1 (would require shipping a test Google account).

## Docs

- `docs/user-guide/features/google-health.md` — modelled on the Spotify doc: prerequisites (Google Cloud project, OAuth client), `hermes auth google-health` walkthrough, tool reference table, troubleshooting.
- `optional-skills/google-health.md` (or co-located under `plugins/google_health/SKILL.md` matching `google_meet`) — teaches the agent when to call each tool, common phrasings ("how did I sleep", "what was my workout", "summarise today's activity").

## Verify-at-implementation-time items

Items where the codelab and screenshot don't fully pin down the API; resolve while building:

1. **Exact filter grammar** for `list_data_points` — codelab shows `filter=exercise.interval.civil_start_time >= "..."`; need to confirm the AND-join and whether `end_time` filtering uses the same field.
2. **Pagination param name** — response uses `nextPageToken`; request param name (`pageToken`? `page_token`?) needs confirmation.
3. **Server-side daily summary endpoint** — codelab nav mentions "roll up daily summaries"; if exposed, prefer over client-side fan-out.
4. **Full list of dataType identifiers** — codelab only confirmed `exercise`. Document the ones encountered while testing; don't hard-code an enum that breaks when Google adds types.
5. **Write payload shape** — codelab excerpt didn't demo writes. Implement as pass-through and validate at the API boundary.

## Out of Scope (explicit YAGNI list)

- Webhook subscription endpoints (`/users/me/subscriptions`) — separate feature once the gateway has an HTTPS callback.
- Bulk export / data dump tooling.
- Multi-user / household reads.
- Caching layer (the agent's own context is the cache; raw API calls are fine for v1 volume).
- Streamlit/web charts.

## Acceptance Criteria

- `hermes auth google-health` runs a browser OAuth flow and writes tokens to `~/.hermes/auth.json` under `providers.google_health`.
- `hermes tools` lists the 5 new tools in a `google_health` toolset.
- With auth configured, the agent answers "summarise yesterday's activity" by calling `health_daily_summary` and reading exercise + sleep + HR data.
- With auth missing, every tool returns the standard "run `hermes auth google-health`" message without crashing.
- All new unit tests pass under `scripts/run_tests.sh`.
