---
name: google_health
description: Read health data from Google's Health Platform API (the API that ships with Fitbit Air). Answer questions about sleep, workouts, heart rate, steps, and other dataTypes. Optionally write manual entries like weight or sleep notes. Use when the user asks about their health metrics, activity, sleep quality, heart rate trends, or wants to log a manual health entry.
version: 0.1.0
platforms:
  - linux
  - macos
  - windows
metadata:
  hermes:
    tags: [health, fitness, google-health, sleep, activity, heart-rate]
---

# google_health

## When to use

The user says any of:

- "how did I sleep last night"
- "what was my sleep quality"
- "summarise today's activity"
- "morning health digest"
- "what's my heart rate trend this week"
- "what was my workout this morning"
- "how many steps did I take yesterday"
- "log that I weigh 78kg"
- "what health data do I have authorized"

## The toolset

The agent has access to five tools that read (and optionally write) health data from Google's Health Platform API. The data types include sleep, heart rate, step count, exercise, SpO2, and others depending on the user's connected devices.

Before any health query, call `health_data_types` if you don't know which dataTypes the user has authorised. This is the right first call when the available data is unclear.

## Mappings: what the user says → which tool

| User says | Tool | Notes |
|---|---|---|
| "how did I sleep" / "what was my sleep last night" | `health_daily_summary` with yesterday's date; narrate `sleep_total_minutes` and `sleep_efficiency_pct` | — |
| "what was my workout this morning" / "summarise today's run" | `health_recent_activity` with `limit=3` | Returns normalized exercise sessions |
| "summarise today's activity" / "morning health digest" | `health_daily_summary` | One-call digest: steps, sleep, HR, calories, SpO2 |
| "what's my heart rate trend this week" | `health_data_query` with `data_type="heart_rate"` and a 7-day range | Supports pagination for longer ranges |
| "log that I weigh 78kg" | `health_write_datapoint` | Requires `--write` scope during auth |
| "what dataTypes do I have" / "what health data is available" | `health_data_types` | Lists authorized data types |

## Prerequisites the user must handle once

```bash
hermes auth google-health              # read-only (sleep, activity, heart rate, etc.)
# or
hermes auth google-health --write      # read + write (add manual entries like weight)
```

A browser tab opens at `accounts.google.com`. After consent, you'll be redirected to a localhost page confirming the login. Tokens are stored in `~/.hermes/auth.json` under `providers.google_health`.

## Tool reference

| Tool | Purpose | Requires `--write` |
|---|---|---|
| `health_data_query` | Query a single dataType (e.g. `exercise`, `sleep`, `heart_rate`, `spo2`) across a time range. Supports pagination. | No |
| `health_data_types` | List which dataTypes the user has authorised. | No |
| `health_daily_summary` | One-call digest of a single day (steps, sleep, HR, calories, SpO2). | No |
| `health_recent_activity` | Most recent N exercise sessions, normalised. | No |
| `health_write_datapoint` | Write a manual entry (e.g. weight, blood pressure, sleep notes). | Yes |

## Important limits

- **Data authorisation:** The user only sees dataTypes they've consented to. If a tool returns "data type not found", try `health_data_types` to see what's available.
- **Rate limits (429):** Google Health API has per-user quotas. Hermes does not retry automatically; wait the `Retry-After` interval and ask again.
- **Token refresh:** Refresh tokens for read-only testing mode expire after 7 days. Either run `hermes auth google-health` weekly or ask the user to move the app to Production mode (requires verification).
- **`health_write_datapoint` requires `--write` scope.** If the user tries to log data without it, they'll get a clear error. Re-run `hermes auth google-health --write`.

## Status check

```bash
hermes auth status google-health
```

Shows whether tokens are present, when the access token expires, and which scopes are active.
