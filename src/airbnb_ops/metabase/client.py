"""Minimal Metabase REST client using only the standard library.

Endpoints used (Metabase 0.6x API): /api/health, /api/session/properties, /api/setup,
/api/session, /api/database, /api/collection, /api/card, /api/dashboard.

The HTTP transport is injectable, so tests run without a Metabase server.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

# (method, url, headers, body bytes or None, timeout seconds) -> (status code, response bytes)
Transport = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, bytes]]


class MetabaseError(RuntimeError):
    """An API call failed. The message carries the status and a trimmed response body."""

    def __init__(self, method: str, path: str, status: int, detail: str) -> None:
        where = f"HTTP {status}" if status else "no response"
        super().__init__(f"{method} {path} failed ({where}): {detail}")
        self.method = method
        self.path = path
        self.status = status
        self.detail = detail


def _urllib_transport(
    method: str, url: str, headers: dict[str, str], data: bytes | None, timeout: float
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:  # 4xx/5xx still carry a useful body
        return exc.code, exc.read()


def _rows(payload: Any) -> list[dict[str, Any]]:
    """List endpoints return either a bare list or {"data": [...]}, depending on version."""
    if isinstance(payload, dict):
        payload = payload.get("data", [])
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


class MetabaseClient:
    def __init__(
        self,
        base_url: str,
        transport: Transport | None = None,
        timeout: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError(f"Metabase URL must start with http:// or https://, got {base_url!r}")
        self.base_url = base_url.rstrip("/")
        self._transport = transport or _urllib_transport
        self._timeout = timeout
        self._sleep = sleep
        self._session: str | None = None

    # -- plumbing -----------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        url = self.base_url + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self._session:
            headers["X-Metabase-Session"] = self._session
        try:
            status, raw = self._transport(method, url, headers, data, self._timeout)
        except OSError as exc:  # connection refused, DNS failure, timeout
            raise MetabaseError(method, path, 0, str(exc)) from exc
        if status >= 400:
            raise MetabaseError(method, path, status, raw.decode("utf-8", "replace")[:500])
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.decode("utf-8", "replace")

    # -- lifecycle ----------------------------------------------------------------------

    def wait_until_healthy(self, timeout: float = 240.0, interval: float = 3.0) -> None:
        """Block until /api/health reports ok. Metabase takes a while to boot on first run."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                response = self._request("GET", "/api/health")
                if isinstance(response, dict) and response.get("status") == "ok":
                    return
                last = f"unexpected response {response!r}"
            except MetabaseError as exc:
                last = str(exc)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Metabase not healthy after {timeout:.0f}s: {last}")
            self._sleep(interval)

    def authenticate(self, email: str, password: str, site_name: str) -> bool:
        """Create the first admin on a fresh instance, otherwise log in.

        Returns True when this call performed the first-time setup.
        """
        props = self._request("GET", "/api/session/properties")
        token = props.get("setup-token") if isinstance(props, dict) else None
        if token:
            response = self._request(
                "POST",
                "/api/setup",
                {
                    "token": token,
                    "user": {
                        "first_name": "Airbnb Ops",
                        "last_name": "Admin",
                        "email": email,
                        "password": password,
                    },
                    "prefs": {"site_name": site_name, "allow_tracking": False},
                },
            )
            first_run = True
        else:
            try:
                response = self._request(
                    "POST", "/api/session", {"username": email, "password": password}
                )
            except MetabaseError as exc:
                if exc.status in (400, 401, 403):
                    raise MetabaseError(
                        exc.method,
                        exc.path,
                        exc.status,
                        f"{exc.detail} -- Metabase is already set up, so METABASE_ADMIN_EMAIL "
                        "and METABASE_ADMIN_PASSWORD must match its existing admin account",
                    ) from exc
                raise
            first_run = False
        session = response.get("id") if isinstance(response, dict) else None
        if not session:
            raise MetabaseError("POST", "/api/session", 200, "response carried no session id")
        self._session = str(session)
        return first_run

    # -- databases, collections ---------------------------------------------------------

    def list_databases(self) -> list[dict[str, Any]]:
        return _rows(self._request("GET", "/api/database"))

    def create_database(self, name: str, details: dict[str, Any]) -> int:
        response = self._request(
            "POST",
            "/api/database",
            {"engine": "postgres", "name": name, "details": details, "is_full_sync": True},
        )
        return int(response["id"])

    def sync_database(self, database_id: int) -> None:
        """Ask Metabase to re-read the schema. Best effort: native-SQL cards work without it."""
        try:
            self._request("POST", f"/api/database/{database_id}/sync_schema")
        except MetabaseError:
            pass

    def list_collections(self) -> list[dict[str, Any]]:
        return _rows(self._request("GET", "/api/collection"))

    def create_collection(self, name: str, description: str) -> int:
        response = self._request(
            "POST", "/api/collection", {"name": name, "description": description}
        )
        return int(response["id"])

    def collection_items(self, collection_id: int, model: str) -> list[dict[str, Any]]:
        return _rows(
            self._request(
                "GET", f"/api/collection/{collection_id}/items", params={"models": model}
            )
        )

    # -- cards and dashboards -----------------------------------------------------------

    def create_card(self, payload: dict[str, Any]) -> int:
        return int(self._request("POST", "/api/card", payload)["id"])

    def update_card(self, card_id: int, payload: dict[str, Any]) -> None:
        self._request("PUT", f"/api/card/{card_id}", payload)

    def create_dashboard(self, name: str, description: str, collection_id: int) -> int:
        response = self._request(
            "POST",
            "/api/dashboard",
            {"name": name, "description": description, "collection_id": collection_id},
        )
        return int(response["id"])

    def set_dashcards(self, dashboard_id: int, dashcards: list[dict[str, Any]]) -> None:
        """Replace the dashboard's whole card layout (negative ids create new dashcards)."""
        self._request("PUT", f"/api/dashboard/{dashboard_id}", {"dashcards": dashcards})
