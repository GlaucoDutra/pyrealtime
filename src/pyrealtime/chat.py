"""Provider-neutral chat contract and an OpenAI Responses API adapter."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Mapping, Protocol, Sequence

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .exceptions import UpstreamError
from .principal import Principal
from .tools import ToolRegistry


class ChatMessage(BaseModel):
    """One replayable, text-only conversation message."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=64_000)

    @field_validator("content")
    @classmethod
    def content_cannot_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content cannot be blank")
        return value


class ChatRequest(BaseModel):
    """Stable request accepted by ``POST /v1/chat``."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    message: str = Field(min_length=1, max_length=64_000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=100)

    @field_validator("message")
    @classmethod
    def message_cannot_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message cannot be blank")
        return value


class ChatToolCall(BaseModel):
    """Application tool activity performed while producing a chat response."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    name: str
    arguments: dict[str, Any]
    status: Literal["completed", "failed"]
    result: Any | None = None
    error: str | None = None


class ChatUsage(BaseModel):
    """Provider-neutral token counts when the provider reports them."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ChatResponse(BaseModel):
    """Stable response returned by ``POST /v1/chat``."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    message: ChatMessage
    tool_calls: list[ChatToolCall] = Field(default_factory=list)
    usage: ChatUsage | None = None


class APIErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str
    request_id: str


class APIErrorResponse(BaseModel):
    """Stable error envelope used by the chat API."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    error: APIErrorDetail


class ChatExecutionError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


ToolAuthorizer = Callable[[str], None | Awaitable[None]]


class ChatBackend(Protocol):
    """Replaceable provider adapter behind the transport-neutral chat route."""

    async def complete(
        self,
        request: ChatRequest,
        *,
        principal: Principal,
        tools: ToolRegistry,
        authorize_tool: ToolAuthorizer,
    ) -> ChatResponse: ...


@dataclass(frozen=True, slots=True)
class OpenAIChatLimits:
    max_tool_rounds: int = 4
    tool_timeout_seconds: float = 120.0
    max_tool_result_chars: int = 32_000
    max_output_tokens: int = 2_048

    def __post_init__(self) -> None:
        if min(self.max_tool_rounds, self.max_tool_result_chars, self.max_output_tokens) <= 0:
            raise ValueError("Chat limits must be positive")
        if self.tool_timeout_seconds <= 0:
            raise ValueError("tool_timeout_seconds must be positive")


class OpenAIResponsesChatBackend:
    """Stateless Responses API adapter with bounded application-tool orchestration."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        instructions: str = "You are a concise and helpful assistant.",
        base_url: str = "https://api.openai.com",
        timeout: float = 120.0,
        limits: OpenAIChatLimits | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key cannot be empty")
        if not model.strip():
            raise ValueError("model cannot be empty")
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._instructions = instructions.strip()
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._limits = limits or OpenAIChatLimits()
        self._http_client = http_client

    async def complete(
        self,
        request: ChatRequest,
        *,
        principal: Principal,
        tools: ToolRegistry,
        authorize_tool: ToolAuthorizer,
    ) -> ChatResponse:
        input_items: list[dict[str, Any]] = [
            {"role": message.role, "content": message.content}
            for message in request.history
        ]
        input_items.append({"role": "user", "content": request.message})
        tool_records: list[ChatToolCall] = []
        usage = ChatUsage()

        for round_number in range(self._limits.max_tool_rounds + 1):
            payload = await self._response(input_items, tools, principal)
            usage = self._add_usage(usage, payload.get("usage"))
            output = payload.get("output", [])
            if not isinstance(output, list):
                raise ChatExecutionError("invalid_provider_response", "The chat provider returned invalid output")
            calls = [item for item in output if isinstance(item, dict) and item.get("type") == "function_call"]
            if not calls:
                text = self._extract_output_text(payload)
                if not text:
                    raise ChatExecutionError("empty_provider_response", "The chat provider returned no assistant message")
                return ChatResponse(
                    message=ChatMessage(role="assistant", content=text),
                    tool_calls=tool_records,
                    usage=usage,
                )
            if round_number >= self._limits.max_tool_rounds:
                raise ChatExecutionError("tool_round_limit", "The chat response exceeded the tool-call round limit")

            input_items.extend(output)
            for item in calls:
                record, provider_output = await self._execute_call(item, principal, tools, authorize_tool)
                tool_records.append(record)
                input_items.append(provider_output)

        raise ChatExecutionError("tool_round_limit", "The chat response exceeded the tool-call round limit")

    async def _execute_call(
        self,
        item: Mapping[str, Any],
        principal: Principal,
        tools: ToolRegistry,
        authorize_tool: ToolAuthorizer,
    ) -> tuple[ChatToolCall, dict[str, Any]]:
        call_id = str(item.get("call_id", "")).strip()
        name = str(item.get("name", "")).strip()
        raw_arguments = item.get("arguments", "{}")
        try:
            arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
            if not isinstance(arguments, dict):
                raise ValueError
        except (TypeError, ValueError, json.JSONDecodeError):
            return self._failed_call(call_id, name, {}, "invalid_tool_arguments")

        authorization = authorize_tool(name)
        if inspect.isawaitable(authorization):
            await authorization

        try:
            result = await asyncio.wait_for(
                tools.execute(name, arguments, principal),
                timeout=self._limits.tool_timeout_seconds,
            )
            serialized = json.dumps(result, default=str, separators=(",", ":"))
            if len(serialized) > self._limits.max_tool_result_chars:
                return self._failed_call(call_id, name, arguments, "tool_result_too_large")
            safe_result = json.loads(serialized)
            record = ChatToolCall(
                id=call_id,
                name=name,
                arguments=arguments,
                status="completed",
                result=safe_result,
            )
            return record, {"type": "function_call_output", "call_id": call_id, "output": serialized}
        except asyncio.TimeoutError:
            return self._failed_call(call_id, name, arguments, "tool_timeout")
        except (KeyError, ValueError):
            return self._failed_call(call_id, name, arguments, "tool_rejected")
        except Exception:
            return self._failed_call(call_id, name, arguments, "tool_failed")

    @staticmethod
    def _failed_call(
        call_id: str,
        name: str,
        arguments: dict[str, Any],
        code: str,
    ) -> tuple[ChatToolCall, dict[str, Any]]:
        record = ChatToolCall(
            id=call_id,
            name=name,
            arguments=arguments,
            status="failed",
            error=code,
        )
        output = json.dumps({"ok": False, "error": code}, separators=(",", ":"))
        return record, {"type": "function_call_output", "call_id": call_id, "output": output}

    async def _response(
        self,
        input_items: Sequence[Mapping[str, Any]],
        tools: ToolRegistry,
        principal: Principal,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._model,
            "input": [dict(item) for item in input_items],
            "store": False,
            "max_output_tokens": self._limits.max_output_tokens,
            "include": ["reasoning.encrypted_content"],
        }
        if self._instructions:
            body["instructions"] = self._instructions
        schemas = tools.schemas()
        if schemas:
            body["tools"] = schemas
            body["tool_choice"] = "auto"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "OpenAI-Safety-Identifier": hashlib.sha256(principal.id.encode()).hexdigest(),
        }
        try:
            if self._http_client is not None:
                response = await self._http_client.post(f"{self._base_url}/v1/responses", headers=headers, json=body)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(f"{self._base_url}/v1/responses", headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise ChatExecutionError("provider_timeout", "The chat provider timed out", status_code=504) from exc
        except httpx.RequestError as exc:
            raise ChatExecutionError("provider_unavailable", "The chat provider could not be reached", status_code=502) from exc
        if not response.is_success:
            raise UpstreamError(
                "OpenAI rejected the chat request",
                status_code=response.status_code,
                response_body=response.text[:1000],
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ChatExecutionError("invalid_provider_response", "The chat provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ChatExecutionError("invalid_provider_response", "The chat provider returned invalid JSON")
        return payload

    @staticmethod
    def _extract_output_text(payload: Mapping[str, Any]) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        parts: list[str] = []
        for item in payload.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    value = content.get("text")
                    if isinstance(value, str):
                        parts.append(value)
        return "\n".join(parts).strip()

    @staticmethod
    def _add_usage(current: ChatUsage, value: Any) -> ChatUsage:
        usage = value if isinstance(value, Mapping) else {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
        return ChatUsage(
            input_tokens=current.input_tokens + input_tokens,
            output_tokens=current.output_tokens + output_tokens,
            total_tokens=current.total_tokens + total_tokens,
        )
