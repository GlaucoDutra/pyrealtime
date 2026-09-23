"""OpenAI Realtime REST gateway used by a trusted application server."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .config import RealtimeSessionConfig
from .exceptions import ConfigurationError, UpstreamError


class OpenAIRealtimeGateway:
    """Create browser credentials and unified WebRTC calls without exposing a standard key."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com",
        timeout: float = 20.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ConfigurationError("OPENAI_API_KEY is required")
        self._api_key = api_key.strip()
        self._base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def _headers(self, safety_identifier: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
        }
        if safety_identifier:
            headers["OpenAI-Safety-Identifier"] = safety_identifier
        return headers

    async def create_client_secret(
        self,
        config: RealtimeSessionConfig,
        *,
        safety_identifier: str | None = None,
    ) -> dict[str, Any]:
        response = await self._client.post(
            f"{self._base_url}/v1/realtime/client_secrets",
            headers={**self._headers(safety_identifier), "Content-Type": "application/json"},
            json=config.to_client_secret_payload(),
        )
        self._raise_for_status(response, "OpenAI rejected the Realtime client-secret request")
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("value"):
            raise UpstreamError("OpenAI returned a client-secret response without value")
        return payload

    async def create_webrtc_call(
        self,
        sdp_offer: str,
        config: RealtimeSessionConfig,
        *,
        safety_identifier: str | None = None,
    ) -> str:
        if not sdp_offer.strip():
            raise ValueError("sdp_offer cannot be empty")
        response = await self._client.post(
            f"{self._base_url}/v1/realtime/calls",
            headers=self._headers(safety_identifier),
            files={
                "sdp": (None, sdp_offer, "application/sdp"),
                "session": (None, json.dumps(config.to_session()), "application/json"),
            },
        )
        self._raise_for_status(response, "OpenAI rejected the WebRTC session request")
        return response.text

    @staticmethod
    def _raise_for_status(response: httpx.Response, message: str) -> None:
        if response.is_success:
            return
        body = response.text[:1000]
        raise UpstreamError(message, status_code=response.status_code, response_body=body)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "OpenAIRealtimeGateway":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

