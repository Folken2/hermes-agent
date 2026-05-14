"""Thin Google Health Platform API helper used by Hermes native tools."""

from __future__ import annotations

from typing import Optional

import httpx

try:
    from hermes_cli.auth import AuthError
except ImportError:  # pragma: no cover — defensive fallback
    class AuthError(RuntimeError):
        pass

try:
    from hermes_cli.auth import resolve_google_health_runtime_credentials
except ImportError:  # pragma: no cover — pre-Task-12 fallback
    def resolve_google_health_runtime_credentials(**_kwargs):
        raise AuthError("Google Health auth not yet wired (Task 12 pending)")


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
