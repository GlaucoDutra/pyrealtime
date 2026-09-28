"""Explicit, deterministic no-key demo components."""

from __future__ import annotations

from typing import Any

from .chat import ChatRequest, ChatResponse, ChatMessage, ChatBackend, ToolAuthorizer
from .config import ServerSettings
from .host import HostHooks
from .principal import Principal
from .tools import ToolRegistry


class DemoChatBackend(ChatBackend):
    """A local echo backend that never contacts an AI provider."""

    label = "DEMO MODE — no AI provider request was made"

    async def complete(
        self,
        request: ChatRequest,
        *,
        principal: Principal,
        tools: ToolRegistry,
        authorize_tool: ToolAuthorizer,
    ) -> ChatResponse:
        del principal, tools, authorize_tool
        return ChatResponse(
            message=ChatMessage(
                role="assistant",
                content=f"[{self.label}] Echo: {request.message}",
            ),
            usage=None,
        )


def create_demo_app(
    *,
    token: str = "local-demo-token",
    cors_origins: tuple[str, ...] = ("http://127.0.0.1:5173", "http://localhost:3000"),
) -> Any:
    """Create a localhost-oriented API with fake chat, auth, hooks, and one tool."""

    try:
        from .api import create_app
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install pyrealtime-ai[api] to run the demo") from exc

    registry = ToolRegistry()

    @registry.tool(
        name="get_status",
        description="Return the status of the no-key demo.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    )
    async def get_status(_: dict[str, Any], principal: Principal) -> dict[str, str]:
        return {"status": "demo-ready", "principal_id": principal.id}

    async def authorize(_: Principal, __: Any) -> bool:
        return True

    return create_app(
        ServerSettings(
            openai_api_key="",
            app_api_key=token,
            cors_origins=cors_origins,
        ),
        tools=registry,
        host=HostHooks(authorize=authorize),
        chat_backend=DemoChatBackend(),
        enable_realtime=False,
    )
