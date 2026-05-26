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
