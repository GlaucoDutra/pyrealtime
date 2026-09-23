"""HTTP client for the application API exposed at app_base_url."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urljoin, urlparse

import httpx

from .exceptions import ConfigurationError, UpstreamError
from .tools import TOOL_NAME_RE


class AppClient:
    def __init__(
        self,
        *,
        app_base_url: str,
        access_token: str | None = None,
        timeout: float = 20.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlparse(app_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError("app_base_url must be an absolute HTTP(S) URL")
        self.app_base_url = app_base_url.rstrip("/")
        self.access_token = access_token
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _url(self, path: str) -> str:
        return urljoin(f"{self.app_base_url}/", path.lstrip("/"))

    def _headers(self) -> dict[str, str]:
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    async def create_realtime_token(self) -> dict[str, Any]:
        response = await self._client.post(self._url("/v1/realtime/token"), headers=self._headers())
        self._raise(response, "Application failed to create a Realtime token")
        return response.json()

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> Any:
        if not TOOL_NAME_RE.fullmatch(name):
            raise ValueError(f"Invalid tool name: {name!r}")
        response = await self._client.post(
            self._url(f"/v1/tools/{name}"),
            headers=self._headers(),
            json=dict(arguments),
        )
        self._raise(response, f"Application tool {name!r} failed")
        return response.json() if response.content else None

    @staticmethod
    def _raise(response: httpx.Response, message: str) -> None:
        if not response.is_success:
            raise UpstreamError(
                message,
                status_code=response.status_code,
                response_body=response.text[:1000],
            )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
