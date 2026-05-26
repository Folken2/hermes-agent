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
