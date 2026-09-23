import asyncio
import json

import httpx
import pytest

from pyrealtime import OpenAIRealtimeGateway, RealtimeSessionConfig, UpstreamError


def test_create_client_secret_uses_current_endpoint_and_safety_identifier():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"value": "ek_test"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = OpenAIRealtimeGateway(api_key="sk-test", http_client=client)
    async def exercise():
        result = await gateway.create_client_secret(
            RealtimeSessionConfig(),
            safety_identifier="hashed-user",
        )
        await client.aclose()
        return result

    result = asyncio.run(exercise())

    request = captured["request"]
    assert request.url.path == "/v1/realtime/client_secrets"
    assert request.headers["OpenAI-Safety-Identifier"] == "hashed-user"
    assert json.loads(request.content)["session"]["type"] == "realtime"
    assert result["value"] == "ek_test"


def test_gateway_surfaces_upstream_failure_without_leaking_key():
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="denied")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = OpenAIRealtimeGateway(api_key="sk-secret", http_client=client)

    async def exercise():
        try:
            return await gateway.create_client_secret(RealtimeSessionConfig())
        finally:
            await client.aclose()

    with pytest.raises(UpstreamError) as exc:
        asyncio.run(exercise())

    assert exc.value.status_code == 401
    assert "sk-secret" not in str(exc.value)
