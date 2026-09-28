"""Generate a minimal, vendor-neutral PyRealtime host application."""

from __future__ import annotations

from pathlib import Path

from ._version import __version__


def _files() -> dict[str, str]:
    wheel = (
        "https://github.com/GlaucoDutra/pyrealtime/releases/download/"
        f"v{__version__}/pyrealtime_ai-{__version__}-py3-none-any.whl"
    )
    return {
        "app.py": '''"""Generated PyRealtime host. Replace the example policy and tool for your app."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from pyrealtime import DemoChatBackend, HostHooks, JevClient, JevTools, Principal, ServerSettings, ToolRegistry
from pyrealtime.api import mount_py_realtime


def enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes"}


settings = ServerSettings.from_env()
demo_mode = enabled("PYREALTIME_DEMO", "true")
tools = ToolRegistry()
if settings.typesafe_api_key:
    JevTools(JevClient(
        api_key=settings.typesafe_api_key,
        model=settings.jev_model,
        timeout=settings.jev_timeout_seconds,
        limits=settings.jev_limits(),
    )).register(tools)


@tools.tool(
    name="get_status",
    description="Return the status of this example application.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
async def get_status(arguments: dict[str, Any], principal: Principal) -> dict[str, str]:
    del arguments
    return {"status": "ready", "principal_id": principal.id}


async def authorize(principal: Principal, request: Any) -> bool:
    # Replace this with ownership, role, or scope checks from your host application.
    del principal, request
    return True


async def lifecycle(event: Any) -> None:
    # Forward safe lifecycle metadata to your telemetry system if needed.
    del event


app = FastAPI(title="My PyRealtime host")
mount_py_realtime(
    app,
    settings,
    path="/ai",
    tools=tools,
    host=HostHooks(authorize=authorize, on_lifecycle=lifecycle),
    chat_backend=DemoChatBackend() if demo_mode else None,
    enable_realtime=not demo_mode,
)
''',
        ".env.example": """# Copy to .env. Never commit real credentials.
PYREALTIME_DEMO=true
OPENAI_API_KEY=
TYPESAFE_API_KEY=
APP_API_KEY=change-this-local-development-token
APP_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:3000
PYREALTIME_CHAT_MODEL=gpt-5-mini
PYREALTIME_MODEL=gpt-realtime-2.1-mini
""",
        ".gitignore": ".env\n.venv/\n__pycache__/\n*.py[cod]\n",
        "requirements.txt": f'pyrealtime-ai[api,auth] @ {wheel}\n',
        "README.md": """# PyRealtime starter

This generated host starts in explicit no-key demo mode. It has shared-key local authentication,
`HostHooks`, and one `get_status` tool. Replace the example authorization rule and tool with your
application logic before production.

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then run:

```bash
uvicorn --env-file .env app:app --reload
```

The API is at `http://127.0.0.1:8000/ai`; OpenAPI is at `/ai/docs`.

Test demo chat:

```bash
curl http://127.0.0.1:8000/ai/v1/chat -H "Authorization: Bearer change-this-local-development-token" -H "Content-Type: application/json" -d '{"message":"hello"}'
```

For the real OpenAI adapters, set `PYREALTIME_DEMO=false` and configure `OPENAI_API_KEY` only on
the server. Replace `APP_API_KEY` with a host authentication callback for public multi-user use.
""",
    }


def generate_starter(destination: str | Path) -> tuple[Path, ...]:
    """Create a starter only in a new or empty directory; existing files are never overwritten."""

    target = Path(destination).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Starter destination is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for relative, content in _files().items():
        path = target / relative
        path.write_text(content, encoding="utf-8", newline="\n")
        created.append(path)
    return tuple(created)
