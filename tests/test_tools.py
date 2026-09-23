import asyncio

import httpx
import pytest

from pyrealtime import AppToolRouter, Principal, ToolRegistry


def test_registry_executes_async_tool_with_principal():
    registry = ToolRegistry()

    @registry.tool(
        name="task_create",
        description="Create a task.",
        parameters={"type": "object", "properties": {}},
    )
    async def task_create(arguments, principal):
        return {"arguments": dict(arguments), "owner": principal.id}

    result = asyncio.run(registry.execute("task_create", {"title": "Test"}, Principal("user-1")))
    assert result == {"arguments": {"title": "Test"}, "owner": "user-1"}
    assert registry.schemas()[0]["name"] == "task_create"


def test_app_router_uses_app_base_url_and_bearer_token():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    router = AppToolRouter(
        app_base_url="https://app.example.com/api",
        app_token="app-token",
        http_client=client,
    )
    async def exercise():
        result = await router.call("task_create", {"title": "Test"})
        await client.aclose()
        return result

    result = asyncio.run(exercise())

    assert str(captured["request"].url) == "https://app.example.com/api/v1/tools/task_create"
    assert captured["request"].headers["Authorization"] == "Bearer app-token"
    assert result == {"ok": True}


def test_app_router_rejects_invalid_tool_name():
    router = AppToolRouter(app_base_url="https://app.example.com")
    with pytest.raises(ValueError):
        router.build_url("../../admin")
