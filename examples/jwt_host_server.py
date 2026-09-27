"""Portable host example: its own JWT auth, authorization rule, and one app tool."""

from __future__ import annotations

import os
from typing import Any

from pyrealtime import HostHooks, JWTAuthenticator, Principal, ServerSettings, ToolRegistry
from pyrealtime.api import create_app


def build_app(
    *,
    settings: ServerSettings | None = None,
    jwt_secret: str | None = None,
    gateway: Any = None,
):
    runtime = settings or ServerSettings.from_env()
    secret = jwt_secret or os.environ.get("EXAMPLE_JWT_SECRET", "")
    if not secret:
        raise RuntimeError("Set EXAMPLE_JWT_SECRET to run this example")

    authenticate = JWTAuthenticator(
        algorithms=("HS256",),
        shared_secret=secret,
        audience="pyrealtime-example",
        issuer="pyrealtime-example-host",
    )
    tools = ToolRegistry()

    @tools.tool(
        name="task_status",
        description="Return the authenticated user's example task status.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
    )
    async def task_status(_: dict[str, Any], principal: Principal) -> dict[str, str]:
        return {"owner_id": principal.id, "status": "ready"}

    async def authorize(principal: Principal, request) -> bool:
        if request.action == "tool.execute" and request.resource == "task_status":
            return "tasks:read" in principal.claims.get("scope", "").split()
        return True

    return create_app(
        runtime,
        tools=tools,
        authenticate=authenticate,
        host=HostHooks(authorize=authorize),
        gateway=gateway,
    )
