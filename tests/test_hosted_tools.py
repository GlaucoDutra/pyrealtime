import asyncio
import json

import httpx

from pyrealtime import OpenAIHostedTools, Principal, ToolRegistry


def test_web_search_uses_openai_hosted_tool_without_app_endpoint():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"id": "resp_1", "output_text": "Current result", "output": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    registry = ToolRegistry()
    OpenAIHostedTools(api_key="sk-test", http_client=client).register(registry)

    async def exercise():
        try:
            return await registry.execute("web_search", {"query": "latest news"}, Principal(id="alice"))
        finally:
            await client.aclose()

    result = asyncio.run(exercise())
    request = captured["request"]
    body = json.loads(request.content)
    assert request.url.path == "/v1/responses"
    assert body["tools"] == [{"type": "web_search", "search_context_size": "low"}]
    assert body["store"] is False
    assert result["output_text"] == "Current result"
    assert request.headers["OpenAI-Safety-Identifier"]


def test_file_search_is_available_only_with_configured_vector_store():
    without_files = ToolRegistry()
    OpenAIHostedTools(api_key="sk-test").register(without_files)
    assert "file_search" not in [schema["name"] for schema in without_files.schemas()]

    with_files = ToolRegistry()
    OpenAIHostedTools(api_key="sk-test", vector_store_ids=["vs_123"]).register(with_files)
    assert "file_search" in [schema["name"] for schema in with_files.schemas()]


def test_image_generation_returns_a_browser_ready_data_uri():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/images/generations"
        return httpx.Response(200, json={
            "data": [{"b64_json": "aW1n", "revised_prompt": "A small blue robot"}],
            "output_format": "png",
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    registry = ToolRegistry()
    OpenAIHostedTools(api_key="sk-test", http_client=client).register(registry)

    async def exercise():
        try:
            return await registry.execute("generate_image", {"prompt": "robot"}, Principal(id="alice"))
        finally:
            await client.aclose()

    result = asyncio.run(exercise())
    assert result["image_data_uri"] == "data:image/png;base64,aW1n"
    assert result["revised_prompt"] == "A small blue robot"
