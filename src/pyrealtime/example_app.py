"""Wheel-installed, independent reference host using only public PyRealtime APIs."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from .api import mount_py_realtime
from .auth import JWTAuthenticator
from .config import ServerSettings
from .host import HostHooks
from .jev import JevClient, JevTools
from .principal import Principal
from .tools import ToolRegistry


def _production_authenticator_from_env() -> JWTAuthenticator | None:
    jwks_url = os.getenv("EXAMPLE_JWKS_URL", "").strip()
    if not jwks_url:
        return None
    audience = os.getenv("EXAMPLE_JWT_AUDIENCE", "").strip()
    issuer = os.getenv("EXAMPLE_JWT_ISSUER", "").strip()
    if not audience or not issuer:
        raise RuntimeError("EXAMPLE_JWT_AUDIENCE and EXAMPLE_JWT_ISSUER are required with EXAMPLE_JWKS_URL")
    return JWTAuthenticator(
        algorithms=("RS256",),
        jwks_url=jwks_url,
        audience=audience,
        issuer=issuer,
    )


def create_example_app(
    *,
    settings: ServerSettings | None = None,
    chat_backend: Any = None,
    gateway: Any = None,
) -> FastAPI:
    """Create a minimal host at ``/ai`` with local-key or JWKS authentication."""

    runtime = settings or ServerSettings.from_env()
    authenticate = _production_authenticator_from_env()
    if authenticate is None and not runtime.app_api_key:
        raise RuntimeError("Set APP_API_KEY for local development, or configure EXAMPLE_JWKS_URL")

    tools = ToolRegistry()
    if runtime.typesafe_api_key:
        JevTools(JevClient(
            api_key=runtime.typesafe_api_key,
            model=runtime.jev_model,
            timeout=runtime.jev_timeout_seconds,
            limits=runtime.jev_limits(),
        )).register(tools)

    @tools.tool(
        name="greet",
        description="Return a short greeting for the authenticated user.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 100}},
            "required": ["name"],
            "additionalProperties": False,
        },
    )
    async def greet(arguments: dict[str, Any], principal: Principal) -> dict[str, str]:
        name = str(arguments.get("name", "")).strip()
        if not name:
            raise ValueError("name is required")
        return {"message": f"Hello, {name}!", "principal_id": principal.id}

    async def authorize(principal: Principal, request: Any) -> bool:
        if authenticate is not None and request.action == "tool.execute":
            return "pyrealtime:tools" in str(principal.claims.get("scope", "")).split()
        return True

    app = FastAPI(title="PyRealtime drop-in example")

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "pyrealtime-drop-in-example", "api": "/ai"}

    mount_py_realtime(
        app,
        runtime,
        path="/ai",
        tools=tools,
        authenticate=authenticate,
        host=HostHooks(authorize=authorize),
        chat_backend=chat_backend,
        gateway=gateway,
    )
    return app


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install pyrealtime-ai[api] to run the example") from exc
    uvicorn.run("pyrealtime.example_app:create_example_app", factory=True, host="127.0.0.1", port=8000)
