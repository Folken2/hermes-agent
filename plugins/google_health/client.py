"""Thin Google Health Platform API helper used by Hermes native tools."""

from __future__ import annotations

from typing import Optional

import httpx

from hermes_cli.auth import (
    AuthError,
    resolve_google_health_runtime_credentials,
)


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

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        allow_retry_on_401: bool = True,
        empty_response: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        response = httpx.request(
            method,
            url,
            headers=self._headers(),
            params=_strip_none(params),
            json=_strip_none(json_body) if json_body is not None else None,
            timeout=30.0,
        )
        if response.status_code == 401 and allow_retry_on_401:
            self._runtime = self._resolve_runtime(force_refresh=True, refresh_if_expiring=False)
            return self.request(
                method, path,
                params=params, json_body=json_body,
                allow_retry_on_401=False,
                empty_response=empty_response,
            )
        if response.status_code == 401:
            raise GoogleHealthAuthRequiredError(
                "Google Health authentication failed or expired."
            )
        if 200 <= response.status_code < 300:
            if not response.content:
                return empty_response or {}
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text}
        body = response.text[:500] if response.text else ""
        try:
            parsed = response.json()
            message = parsed.get("error", {}).get("message") or body or "Google Health API error"
        except ValueError:
            message = body or f"Google Health API error ({response.status_code})"
        err = GoogleHealthAPIError(
            message,
            status_code=response.status_code,
            response_body=body,
        )
        err.path = path
        raise err

    def list_data_points(
        self,
        data_type: str,
        *,
        start_iso: str,
        end_iso: str,
        page_token: Optional[str] = None,
        page_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        filter_expr = (
            f'{data_type}.interval.civil_start_time >= "{start_iso}" '
            f'AND {data_type}.interval.civil_start_time <= "{end_iso}"'
        )
        return self.request(
            "GET",
            f"/users/me/dataTypes/{data_type}/dataPoints",
            params={
                "filter": filter_expr,
                "pageToken": page_token,
                "pageSize": page_size,
            },
        )

    def list_authorized_data_types(self) -> Dict[str, Any]:
        return self.request("GET", "/users/me/dataTypes")

    def write_data_point(self, data_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.request(
            "POST",
            f"/users/me/dataTypes/{data_type}/dataPoints",
            json_body=payload,
        )


def _strip_none(d: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if d is None:
        return None
    return {k: v for k, v in d.items() if v is not None}
