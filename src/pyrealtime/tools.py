"""Structured tool definitions, execution, and generic application routing."""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import quote, urljoin, urlparse

import httpx

from .exceptions import ConfigurationError, UpstreamError
from .principal import Principal

TOOL_NAME_RE = re.compile(r"^[a-z0-9_.-]{1,64}$")
ToolHandler = Callable[[Mapping[str, Any], Principal], Any | Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: ToolHandler

    def __post_init__(self) -> None:
        if not TOOL_NAME_RE.fullmatch(self.name):
            raise ValueError(f"Invalid tool name: {self.name!r}")
        if self.parameters.get("type") != "object":
            raise ValueError("Tool parameters must be a JSON Schema object")

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": dict(self.parameters),
        }


class ToolRegistry:
    """Register and execute local application tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> ToolDefinition:
        if definition.name in self._tools:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._tools[definition.name] = definition
        return definition

    def tool(
        self,
        *,
        name: str,
        description: str,
        parameters: Mapping[str, Any],
    ) -> Callable[[ToolHandler], ToolHandler]:
        def decorator(handler: ToolHandler) -> ToolHandler:
            self.register(ToolDefinition(name, description, parameters, handler))
            return handler

        return decorator

    def schemas(self) -> list[dict[str, Any]]:
        return [definition.to_openai() for definition in self._tools.values()]

    async def execute(self, name: str, arguments: Mapping[str, Any], principal: Principal) -> Any:
        try:
            definition = self._tools[name]
        except KeyError as exc:
            raise KeyError(f"Unknown tool: {name}") from exc
        result = definition.handler(arguments, principal)
        if inspect.isawaitable(result):
            return await result
        return result


class AppToolRouter:
    """Forward tool calls to a generic application API rooted at app_base_url."""

    def __init__(
        self,
        *,
        app_base_url: str,
        app_token: str | None = None,
        endpoint_template: str = "/v1/tools/{tool_name}",
        timeout: float = 20.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        parsed = urlparse(app_base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError("app_base_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConfigurationError("app_base_url cannot contain credentials, query, or fragment")
        if "{tool_name}" not in endpoint_template:
            raise ConfigurationError("endpoint_template must contain {tool_name}")

        self.app_base_url = app_base_url.rstrip("/")
        self.app_token = app_token
        self.endpoint_template = endpoint_template
        self._origin = (parsed.scheme.lower(), parsed.netloc.lower())
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout)

    def build_url(self, tool_name: str) -> str:
        if not TOOL_NAME_RE.fullmatch(tool_name):
            raise ValueError(f"Invalid tool name: {tool_name!r}")
        path = self.endpoint_template.format(tool_name=quote(tool_name, safe=""))
        url = urljoin(f"{self.app_base_url}/", path.lstrip("/"))
        parsed = urlparse(url)
        if (parsed.scheme.lower(), parsed.netloc.lower()) != self._origin:
            raise ConfigurationError("Tool endpoint escaped app_base_url")
        return url

    async def call(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        access_token: str | None = None,
    ) -> Any:
        headers = {"Content-Type": "application/json"}
        token = access_token or self.app_token
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = await self._client.post(self.build_url(tool_name), headers=headers, json=dict(arguments))
        if not response.is_success:
            raise UpstreamError(
                f"Application tool {tool_name!r} failed",
                status_code=response.status_code,
                response_body=response.text[:1000],
            )
        if not response.content:
            return None
        content_type = response.headers.get("content-type", "")
        return response.json() if "json" in content_type else response.text

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

