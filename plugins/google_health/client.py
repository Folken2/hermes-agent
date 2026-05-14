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
