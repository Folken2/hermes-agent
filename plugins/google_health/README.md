# Google Health Plugin

Native integration with Google's Health Platform API
(`health.googleapis.com/v4`) — the API that ships with Fitbit Air and
future Google health hardware.

**Setup:** `hermes auth google-health` (add `--write` if you want
the agent to log manual entries like weight or sleep notes).

**Tools added:** `health_data_query`, `health_data_types`,
`health_daily_summary`, `health_recent_activity`, `health_write_datapoint`.

See [docs/user-guide/features/google-health.md](../../website/docs/user-guide/features/google-health.md) for full setup.
