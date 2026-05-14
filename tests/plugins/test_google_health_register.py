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
