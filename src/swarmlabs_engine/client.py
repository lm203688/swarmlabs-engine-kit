"""SwarmLabs Engine HTTP client.

Thin, dependency-free client for the SwarmLabs `/api/v2/` surface.
The engine deployment URL is supplied by the caller — this client is the
open-source interface and works against any SwarmLabs engine deployment.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

try:  # Python 3.8+
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
except ImportError:  # pragma: no cover
    from urllib2 import Request, urlopen, HTTPError, URLError  # type: ignore


DEFAULT_BASE_URL = "https://your-swarmlabs-engine.example.com"


class SwarmLabsError(RuntimeError):
    """Raised on non-2xx responses or transport errors."""

    def __init__(self, message: str, status: Optional[int] = None, body: Any = None):
        super().__init__(message)
        self.status = status
        self.body = body


class SwarmLabsClient:
    """Client for the SwarmLabs physics-informed engine API."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    # ----- internal -----------------------------------------------------
    def _request(self, method: str, path: str, body: Optional[dict] = None) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as e:  # noqa: BLE001
            detail = e.read().decode("utf-8", "replace") if e.fp else ""
            raise SwarmLabsError(f"HTTP {e.code}: {detail}", status=e.code, body=detail) from e
        except URLError as e:  # noqa: BLE001
            raise SwarmLabsError(f"transport error: {e.reason}") from e
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    # ----- endpoints ----------------------------------------------------
    def list_engines(self) -> Dict[str, Any]:
        """GET/POST /api/v2/list — engines and physics-model coverage."""
        return self._request("GET", "/api/v2/list")

    def run(self, engine: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/v2/run/{engine} — real physics-informed prediction."""
        return self._request("POST", f"/api/v2/run/{engine}", params)

    def physics_informed(self, engine: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/v2/pi/{engine} — physics-informed variant (honest models)."""
        return self._request("POST", f"/api/v2/pi/{engine}", params)

    def sweep(self, engine: str, params: Dict[str, Any], n: int = 20) -> Dict[str, Any]:
        """POST /api/v2/sweep/{engine} — parameter sweep for trend analysis."""
        payload = dict(params)
        payload["_n"] = n
        return self._request("POST", f"/api/v2/sweep/{engine}", payload)

    def multifidelity(self, engines: list, params: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/v2/multifidelity — cross-engine multi-fidelity query."""
        return self._request(
            "POST", "/api/v2/multifidelity", {"engines": engines, "params": params}
        )

    def measure(self, engine: str, params: Dict[str, Any], value: float) -> Dict[str, Any]:
        """POST /api/v2/measure/{engine} — record a real measurement."""
        payload = dict(params)
        payload["measured_value"] = value
        return self._request("POST", f"/api/v2/measure/{engine}", payload)
