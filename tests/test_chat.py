import asyncio
import json

import httpx
import pytest

from pyrealtime import (
    ChatRequest,
    OpenAIChatLimits,
    OpenAIResponsesChatBackend,
    Principal,
    ToolRegistry,
)


@pytest.mark.asyncio
async def test_openai_adapter_runs_authorized_tool_and_returns_neutral_schema():
    bodies = []
    responses = [
        {
            "id": "resp_1",
            "output": [{
                "type": "function_call",
                "call_id": "call_1",
                "name": "greet",
                "arguments": '{"name":"Ada"}',
            }],
            "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
        },
        {
            "id": "resp_2",
            "output_text": "Hello, Ada!",
            "output": [],
            "usage": {"input_tokens": 8, "output_tokens": 3, "total_tokens": 11},
        },
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=responses.pop(0))

    registry = ToolRegistry()

    @registry.tool(
        name="greet",
        description="Greet a person",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    )
    async def greet(arguments, principal):
        return {"message": f"Hello, {arguments['name']}!", "owner": principal.id}

    authorized = []

    async def authorize(name):
        authorized.append(name)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenAIResponsesChatBackend(
            api_key="sk-test",
            model="test-model",
            http_client=client,
        )
        result = await backend.complete(
            ChatRequest(message="Say hello", history=[{"role": "user", "content": "My name is Ada"}]),
            principal=Principal(id="user-1"),
            tools=registry,
            authorize_tool=authorize,
        )

    assert result.message.content == "Hello, Ada!"
    assert result.tool_calls[0].status == "completed"
    assert result.tool_calls[0].result["owner"] == "user-1"
    assert result.usage.total_tokens == 25
    assert authorized == ["greet"]
    assert bodies[0]["store"] is False
    assert bodies[1]["input"][-1]["type"] == "function_call_output"


@pytest.mark.asyncio
async def test_chat_tool_timeout_is_bounded_and_redacted():
    responses = [
        {"output": [{"type": "function_call", "call_id": "c1", "name": "slow", "arguments": "{}"}]},
        {"output_text": "The tool timed out.", "output": []},
    ]

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=responses.pop(0))

    tools = ToolRegistry()

    @tools.tool(name="slow", description="Slow", parameters={"type": "object", "properties": {}})
    async def slow(_, __):
        await asyncio.sleep(0.05)
        return {"secret": "must-not-return"}

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenAIResponsesChatBackend(
            api_key="sk-test",
            model="test-model",
            http_client=client,
            limits=OpenAIChatLimits(tool_timeout_seconds=0.001),
        )
        result = await backend.complete(
            ChatRequest(message="Run it"),
            principal=Principal(id="user-1"),
            tools=tools,
            authorize_tool=lambda _: None,
        )

    assert result.tool_calls[0].status == "failed"
    assert result.tool_calls[0].error == "tool_timeout"
    assert result.tool_calls[0].result is None


@pytest.mark.asyncio
async def test_chat_tool_authorization_happens_before_execution():
    response = {
        "output": [{"type": "function_call", "call_id": "c1", "name": "protected", "arguments": "{}"}],
    }

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response)

    tools = ToolRegistry()
    executed = False

    @tools.tool(name="protected", description="Protected", parameters={"type": "object", "properties": {}})
    async def protected(_, __):
        nonlocal executed
        executed = True
        return {"ok": True}

    async def deny(_: str) -> None:
        raise PermissionError("denied")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        backend = OpenAIResponsesChatBackend(api_key="sk-test", model="test-model", http_client=client)
        with pytest.raises(PermissionError, match="denied"):
            await backend.complete(
                ChatRequest(message="Run it"),
                principal=Principal(id="user-1"),
                tools=tools,
                authorize_tool=deny,
            )

    assert executed is False
