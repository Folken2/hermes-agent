# Google Health

Hermes can read (and optionally write) your health data from Google's Health Platform API — the API that ships with Fitbit Air. Once authenticated, the agent answers questions like "how did I sleep last night" or "summarise today's activity" directly from device data.

## Prerequisites

1. A Google Cloud project with the Health Platform API enabled. Create one at <https://console.cloud.google.com>.
2. An OAuth 2.0 Client ID of type **Desktop app**, created at <https://console.cloud.google.com/apis/credentials>.
3. Your Google account added as a test user on the OAuth consent screen (while the app is in "Testing" mode).

## Setup

### One-shot: `hermes tools`

The fastest path. Run:

```bash
hermes tools
```

Scroll to `❤️ Google Health`, press space to toggle it on, then `s` to save. Hermes drops you straight into the OAuth flow and walks you through creating a Cloud project and OAuth client if needed. Once you finish, the toolset is enabled AND authenticated in one pass.

If you prefer to do the steps separately (or you're re-authing later), use the two-step flow below.

### Two-step flow

#### 1. Create a Google Cloud project

1. Visit <https://console.cloud.google.com> and sign in with your Google account.
2. Click the project dropdown at the top and select **NEW PROJECT**.
3. Name it anything (e.g., `hermes-health`) and click **CREATE**.
4. Wait for the project to initialize, then open it.

#### 2. Enable the Health Platform API

1. In your new project, go to **APIs & Services** → **Library**.
2. Search for "Health Platform API" and click on it.
3. Click **ENABLE**.

#### 3. Create an OAuth 2.0 Client ID

1. Go back to **APIs & Services** → **Credentials**.
2. Click **+ CREATE CREDENTIALS** → **OAuth client ID**.
3. If prompted, configure the OAuth consent screen first:
   - User type: **Internal** (or **External** if you want to publish later)
   - Fill in the required fields (app name, user support email, etc.)
   - Click **SAVE AND CONTINUE** through each step
4. When you reach the "Create OAuth client ID" dialog:
   - Application type: **Desktop application**
   - Name it anything (e.g., `hermes-agent`)
   - Click **CREATE**
5. Copy the **Client ID** from the dialog that appears. You'll paste this into Hermes next.

#### 4. Add yourself as a test user

1. In **APIs & Services** → **OAuth consent screen**, scroll to **Test users**.
2. Click **+ ADD USERS** and enter your Google account email.
3. Click **SAVE**.

#### 5. Configure Hermes and authenticate

```bash
hermes config set google_health.client_id YOUR_CLIENT_ID
```

Replace `YOUR_CLIENT_ID` with the value you copied in step 3.5.

Then run the OAuth login (read-only):

```bash
hermes auth google-health
```

Or grant write access (so the agent can log manual entries):

```bash
hermes auth google-health --write
```

A browser tab opens at `accounts.google.com`. Select your account and click **Continue** to consent. You'll be redirected to a localhost page confirming the login. Tokens are stored in `~/.hermes/auth.json` under `providers.google_health`.

## Verify

```bash
hermes auth status google-health
```

Shows whether tokens are present, when the access token expires, and which scopes are active (read-only or read/write).

## Using it

Once logged in, the agent has access to five Google Health tools. You talk to the agent naturally — it picks the right tool and action.

```
> how did I sleep last night
> what was my workout this morning
> summarise today's activity
> what's my heart rate trend this week
> log that I weigh 78kg
> what health data am I authorised for
```

## Tools

| Tool | What it does |
| ---- | ------------ |
| `health_data_query` | Query a single dataType (e.g. `exercise`, `sleep`, `heart_rate`, `spo2`) across a time range. Supports pagination for large result sets. |
| `health_data_types` | List which dataTypes the user has authorised. Use this first if you're unsure what data is available. |
| `health_daily_summary` | One-call digest of a single day (steps, sleep, HR, calories, SpO2). Returns normalized metrics. |
| `health_recent_activity` | Most recent N exercise sessions, normalized to a common format. |
| `health_write_datapoint` | Write a manual entry (e.g. weight, blood pressure, sleep notes). Requires `--write` scope. |

## Scheduling: Google Health + cron

Because Google Health tools are regular Hermes tools, a cron job running in a Hermes session can trigger health queries on any schedule. No new code needed.

### Daily morning health report

```bash
hermes cron add \
  --name "morning-health" \
  "0 7 * * *" \
  "Summarise yesterday's sleep and today's morning activity so far. Include heart rate and steps."
```

What happens at 7am every day:
1. Cron spins up a headless Hermes session.
2. Agent reads the prompt, calls `health_daily_summary` for yesterday and today, plus `health_recent_activity` to fetch this morning's exercise.
3. Agent summarizes the results and (optionally) sends a message to a configured channel. Total cost: one session, a few tool calls, no human input.

### Weekly health trends

```bash
hermes cron add \
  --name "weekly-health" \
  "0 9 * * 0" \
  "Analyse my heart rate and sleep efficiency trends over the past week."
```

Full cron reference: [Cron Jobs](./cron).

## Data types

Common dataTypes that Google Health API supports (availability depends on your connected devices):

| Data type | Source | Notes |
|---|---|---|
| `sleep` | Fitbit Air, smartwatch | Sleep sessions, total minutes, efficiency percentage |
| `heart_rate` | Fitbit Air, smartwatch | BPM samples, typically 1/min |
| `steps` | Fitbit Air, smartwatch, phone | Step count per time bucket |
| `calories` | Fitbit Air, smartwatch | Burnt calories |
| `spo2` | Fitbit Air, smartwatch | Blood oxygen percentage |
| `exercise` | Fitbit Air, smartwatch | Named workouts (running, cycling, yoga, etc.) with duration and intensity |
| `weight` | Manual entry, smart scale | Weight in kg/lbs |
| `blood_pressure` | Manual entry, smart device | Systolic and diastolic |

## Troubleshooting

**"Google Health authentication failed or expired"** — your access token expired and refresh failed. Re-run `hermes auth google-health`.

**"Google Health rejected the request because the current auth scope is insufficient"** — you authenticated read-only but tried a write tool. Re-run `hermes auth google-health --write`.

**"Data type not found"** — the dataType you queried isn't in the user's authorised list. Call `health_data_types` first to see what's available.

**Rate limit (429)** — the API has per-user quotas. Hermes does not retry automatically; wait the `Retry-After` interval (usually 60 seconds) and ask again.

**Token not refreshing** — Google refresh tokens for "Testing"-mode apps expire after 7 days. Either publish the OAuth consent screen (requires verification) or re-run `hermes auth google-health` weekly. Alternatively, move the Cloud project to Production mode (requires domain verification).

**"No active device found"** — you don't have a Fitbit Air or compatible smartwatch connected to your Google account, or it's not syncing data. Make sure your device is paired and the Health app has permission to read from it.

## Where things live

| File | Contents |
|------|----------|
| `~/.hermes/auth.json` → `providers.google_health` | access token, refresh token, expiry, scopes |
| `~/.hermes/.config` → `google_health.client_id` | your OAuth Client ID |
| Google Cloud Console | <https://console.cloud.google.com> — your project, credentials, API enablement |

## Sign out

```bash
hermes auth logout google-health
```

Removes tokens from `~/.hermes/auth.json`. To also clear the client ID config, run:

```bash
hermes config delete google_health.client_id
```

To revoke the app on Google's side, visit [Connected apps & sites](https://myaccount.google.com/permissions) and remove "hermes-agent" from the list.
