import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from pyrealtime import (
    JevChoiceQuestion,
    JevClient,
    JevLimits,
    JevNoulQuestion,
    JevScoreQuestion,
    JevTools,
    Principal,
    ToolRegistry,
    UpstreamError,
)


def test_open_call_sends_typed_questions_and_returns_typed_answers():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json={
            "model": "jev-1.13.0",
            "answers": {
                "department": {
                    "type": "choice",
                    "choice": "technical",
                    "confidence": 0.78,
                    "probabilities": {"technical": 0.85, "billing": 0.15},
                },
                "frustration": {
                    "type": "score",
                    "score": 1.0,
                    "confidence": 1.0,
                    "legend": {"0": "Calm", "1": "Frustrated"},
                    "probabilities": {"0": 0.0, "1": 1.0},
                },
                "urgent": {"type": "noul", "noul": 1.0},
            },
            "usage": {"input_tokens": 20, "output_tokens": 7},
        })

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = JevClient(api_key="ts-secret", http_client=http_client)

    async def exercise():
        try:
            return await client.system_one(
                state={"message": "Integration failed. Help ASAP."},
                questions={
                    "department": JevChoiceQuestion(
                        instructions="Which team?",
                        criteria={"billing": "Payment", "technical": "Integration"},
                    ),
                    "frustration": JevScoreQuestion(
                        instructions="How frustrated?", criteria=["Calm", "Frustrated"]
                    ),
                    "urgent": JevNoulQuestion(instructions="Is it urgent?"),
                },
            )
        finally:
            await http_client.aclose()

    response = asyncio.run(exercise())
    request = captured["request"]
    body = json.loads(request.content)
    assert request.url == "https://api.typesafe.ai/v1/systemone"
    assert request.headers["Authorization"] == "Bearer ts-secret"
    assert body["model"] == "jev-latest"
    assert body["questions"]["department"]["type"] == "choice"
    assert response.answers["department"].choice == "technical"
    assert response.answers["frustration"].score == 1.0
    assert response.answers["urgent"].noul == 1.0


def test_agent_tool_is_open_ended_but_uses_server_model_and_key():
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "jev-server-model"
        assert "model" not in body["questions"]["decision"]
        return httpx.Response(200, json={
            "model": "jev-server-model-1",
            "answers": {"decision": {"type": "noul", "noul": -0.5}},
            "usage": {"input_tokens": 5, "output_tokens": 1},
        })

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    registry = ToolRegistry()
    JevTools(JevClient(api_key="ts-secret", model="jev-server-model", http_client=http_client)).register(registry)
    schema = registry.schemas()[0]
    assert schema["name"] == "jev_decide"
    assert "model" not in schema["parameters"]["properties"]

    async def exercise():
        try:
            return await registry.execute(
                "jev_decide",
                {
                    "state": "A user-visible state chosen at runtime",
                    "questions": {"decision": {"type": "noul", "instructions": "Should this proceed?"}},
                },
                Principal(id="alice"),
            )
        finally:
            await http_client.aclose()

    result = asyncio.run(exercise())
    assert result["answers"]["decision"]["noul"] == -0.5


def test_limits_reject_state_and_question_count_before_network():
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = JevClient(
        api_key="ts-secret",
        limits=JevLimits(max_state_bytes=8, max_questions=1),
        http_client=http_client,
    )

    async def exercise():
        try:
            with pytest.raises(ValueError, match="state cannot exceed"):
                await client.system_one(
                    state="far too long",
                    questions={"q": {"type": "noul", "instructions": "Decide"}},
                )
            with pytest.raises(ValueError, match="questions cannot exceed"):
                await client.system_one(
                    state="ok",
                    questions={
                        "one": {"type": "noul", "instructions": "One"},
                        "two": {"type": "noul", "instructions": "Two"},
                    },
                )
        finally:
            await http_client.aclose()

    asyncio.run(exercise())
    assert calls == 0


def test_invalid_question_shape_is_rejected():
    with pytest.raises(ValidationError):
        JevChoiceQuestion(instructions="Choose", criteria={"only_one": "Invalid"})


def test_provider_error_is_redacted_and_timeout_is_controlled():
    async def rejected(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='secret state and token ts-secret')

    rejected_client = httpx.AsyncClient(transport=httpx.MockTransport(rejected))
    client = JevClient(api_key="ts-secret", http_client=rejected_client)

    async def exercise_rejection():
        try:
            with pytest.raises(UpstreamError) as raised:
                await client.system_one(
                    state="secret state",
                    questions={"q": {"type": "noul", "instructions": "Decide"}},
                )
            assert raised.value.status_code == 400
            assert raised.value.response_body == ""
            assert "secret" not in str(raised.value)
        finally:
            await rejected_client.aclose()

    asyncio.run(exercise_rejection())

    async def timed_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider details", request=request)

    timeout_client = httpx.AsyncClient(transport=httpx.MockTransport(timed_out))
    timeout_jev = JevClient(api_key="ts-secret", http_client=timeout_client)

    async def exercise_timeout():
        try:
            with pytest.raises(UpstreamError, match="timed out") as raised:
                await timeout_jev.system_one(
                    state="state",
                    questions={"q": {"type": "noul", "instructions": "Decide"}},
                )
            assert raised.value.status_code == 504
        finally:
            await timeout_client.aclose()

    asyncio.run(exercise_timeout())
