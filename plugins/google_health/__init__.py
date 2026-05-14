"""Google Health Platform API integration plugin — bundled, auto-loaded.

Mirrors the spotify plugin: PKCE OAuth via `hermes auth google-health`,
5 tools gated on stored credentials, runtime check prevents dispatch
when the user has not authenticated.
"""

from __future__ import annotations


def register(ctx) -> None:
    """Register Google Health tools. Filled in by later tasks."""
    return None
