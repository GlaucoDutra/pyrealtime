# PyRealtime

PyRealtime is a reusable Python backend for authenticated chat, OpenAI Realtime WebRTC sessions, application tools, and prepared file attachments. It keeps provider credentials and authorization on the server and exposes stable, client-neutral HTTP contracts.

The canonical integration reference is [docs/LLM_USAGE.md](docs/LLM_USAGE.md). This README is the shortest working path.

## Drop-in contract

- Python 3.10–3.13.
- A pinned `pyrealtime-ai` wheel; imports use `pyrealtime`.
- The `api` extra for FastAPI/Uvicorn, `auth` for JWT/JWKS verification, and `files` only when document extraction is needed.
- A server-side OpenAI API key for the default chat and Realtime adapters.
- Host-provided authentication, authorization policy, tools, persistence, and billing policy.

No source checkout, frontend repository, database, tenant model, or specific identity provider is required.

## Install 0.2.1

The supported public route is the immutable GitHub release wheel:

```bash
python -m venv .venv
python -m pip install "pyrealtime-ai[api,auth] @ https://github.com/GlaucoDutra/pyrealtime/releases/download/v0.2.1/pyrealtime_ai-0.2.1-py3-none-any.whl"
```

PyPI publication is pending. `pip install pyrealtime-ai==0.2.1` is not a supported command until the package is visible on PyPI.

## Smallest standalone API

```python
from pyrealtime import Principal, ServerSettings, ToolRegistry
from pyrealtime.api import create_app

settings = ServerSettings(
    openai_api_key="read-from-your-secret-manager",
    app_api_key="local-development-token",
    cors_origins=("http://localhost:3000",),
)
tools = ToolRegistry()

@tools.tool(
    name="get_status",
    description="Return service status.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
async def get_status(arguments, principal: Principal):
    return {"status": "ready", "principal_id": principal.id}

app = create_app(settings, tools=tools)
```

Run `uvicorn your_module:app`. Send the development token to protected endpoints:

```bash
curl http://127.0.0.1:8000/v1/chat \
  -H "Authorization: Bearer local-development-token" \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the service status?","history":[]}'
```

## Mount into an existing FastAPI application

```python
from fastapi import FastAPI
from pyrealtime import ServerSettings, ToolRegistry
from pyrealtime.api import mount_py_realtime

app = FastAPI()
mount_py_realtime(
    app,
    ServerSettings.from_env(),
    path="/ai",
    tools=ToolRegistry(),
    authenticate=verify_your_request_and_return_principal,
)
```

The mounted routes are under `/ai/v1/...`; documentation is at `/ai/docs`. Use `HostHooks` for authorization and lifecycle events. Inject a `RateLimiter`, `UsageSink`, `AttachmentStore`, or `ChatBackend` only when the host needs a different implementation.

## Installed reference app

The wheel includes an independent example with one `greet` tool:

```bash
set OPENAI_API_KEY=sk-server-only
set APP_API_KEY=local-development-token
pyrealtime-example
```

On PowerShell use `$env:OPENAI_API_KEY=...` and `$env:APP_API_KEY=...`. The API is mounted at `http://127.0.0.1:8000/ai`. For a production-style verifier, set `EXAMPLE_JWKS_URL`, `EXAMPLE_JWT_AUDIENCE`, and `EXAMPLE_JWT_ISSUER`; JWT tool access requires the `pyrealtime:tools` scope.

## Public routes

- `GET /v1/health`
- `POST /v1/chat`
- `POST /v1/realtime/token`
- `POST /v1/realtime/session`
- `POST /v1/tools/{tool_name}`
- `POST /v1/files/prepare` when `AttachmentProcessor` is enabled

All routes except health fail closed when authentication is not configured. The host owns accounts, databases, tenant/company rules, quotas, billing, and presentation.

PyRealtime is MIT licensed. Release and compatibility details are in [CHANGELOG.md](CHANGELOG.md), [DEPENDENCY_POLICY.md](DEPENDENCY_POLICY.md), and [RELEASING.md](RELEASING.md).
