# PyRealtime complete usage guide

This document is the canonical operating guide for humans and language models that need to install, run, integrate, extend, or troubleshoot PyRealtime.

## 1. What PyRealtime is

PyRealtime is a Python library and optional FastAPI application for browser-based OpenAI Realtime applications.

It owns reusable server responsibilities:

- Keeping the standard `OPENAI_API_KEY` private.
- Creating OpenAI Realtime sessions.
- Authenticating application users.
- Publishing tool schemas and executing backend tools.
- Calling OpenAI hosted tools through the Responses and Images APIs.
- Validating, extracting, normalizing, and chunking uploaded files.

It does not own browser responsibilities:

- Microphone capture.
- WebRTC peer connections in the browser.
- Remote audio playback.
- DOM rendering.
- Three.js avatars and device-local actions.

The reference browser implementation is [pyrealtime-web](https://github.com/GlaucoDutra/pyrealtime-web). Read its `docs/LLM_USAGE.md` for frontend integration.

## 2. Repository contract

The public Python package is in `src/pyrealtime`.

| Path | Purpose |
| --- | --- |
| `src/pyrealtime/config.py` | Realtime session and server configuration |
| `src/pyrealtime/gateway.py` | OpenAI Realtime HTTP/WebRTC gateway |
| `src/pyrealtime/api.py` | Optional FastAPI application factory |
| `src/pyrealtime/tools.py` | Tool schemas, registry, execution, and application routing |
| `src/pyrealtime/hosted_tools.py` | Web search, file search, image generation, and single backend model calls |
| `src/pyrealtime/attachments.py` | Reusable file validation and extraction |
| `examples/prototype_server.py` | Complete local demonstration server |
| `examples/api_server.py` | Minimal integration server |

Do not place DOM, microphone, WebRTC rendering, or Three.js logic in this repository. Follow `ARCHITECTURE.md`.

## 3. Fastest complete local setup

The easiest Windows setup uses both repositories as sibling directories:

```text
parent-directory/
  pyrealtime/
  pyrealtime-web/
```

Clone them:

```powershell
git clone https://github.com/GlaucoDutra/pyrealtime.git
git clone https://github.com/GlaucoDutra/pyrealtime-web.git
cd pyrealtime-web
.\scripts\run-local.ps1
```

The launcher:

1. Securely prompts for `OPENAI_API_KEY` when it is not already set.
2. Creates `.venv-prototype` inside `pyrealtime-web`.
3. Installs the local PyRealtime package.
4. Starts the backend at `http://127.0.0.1:8000`.
5. Starts the frontend at `http://127.0.0.1:5173`.
6. Opens the browser.
7. Stops both owned processes when Enter is pressed in the launcher window.

The local launcher enables anonymous access only for the local prototype. Do not copy that authentication mode into a public deployment.

## 4. Manual backend setup

Requirements:

- Python 3.10 through 3.13.
- An OpenAI project API key with access to the configured models.

Install the pinned GitHub release without cloning the source:

```bash
python -m venv .venv
python -m pip install "pyrealtime-ai[api,auth,files] @ https://github.com/GlaucoDutra/pyrealtime/releases/download/v0.2.0/pyrealtime_ai-0.2.0-py3-none-any.whl"
```

After the PyPI trusted publisher is enabled, the equivalent command is:

```bash
python -m pip install "pyrealtime-ai[api,auth,files]==0.2.0"
```

For contributors installing from a clone:

```bash
python -m venv .venv
```

Activate on PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[api,auth,files,dev]"
```

Activate on macOS or Linux:

```bash
source .venv/bin/activate
python -m pip install -e ".[api,auth,files,dev]"
```

`ServerSettings.from_env()` reads process environment variables. It does not load `.env` files itself. Export variables in the shell, use your platform's secret manager, or load a `.env` file in your host application before calling `ServerSettings.from_env()`.

PowerShell example:

```powershell
$env:OPENAI_API_KEY = "sk-your-server-key"
$env:APP_API_KEY = "local-development-token"
$env:APP_CORS_ORIGINS = "http://127.0.0.1:5173"
python -m uvicorn examples.prototype_server:app --host 127.0.0.1 --port 8000
```

macOS/Linux example:

```bash
export OPENAI_API_KEY="sk-your-server-key"
export APP_API_KEY="local-development-token"
export APP_CORS_ORIGINS="http://127.0.0.1:5173"
python -m uvicorn examples.prototype_server:app --host 127.0.0.1 --port 8000
```

Verify the server:

```bash
curl http://127.0.0.1:8000/v1/health
```

Expected response:

```json
{"status":"ok","service":"pyrealtime","version":"0.2.0"}
```

Interactive FastAPI documentation is available at `http://127.0.0.1:8000/docs` while the example server is running.

## 5. Environment variables

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | Yes | Empty | Standard OpenAI key. Server only. |
| `APP_API_KEY` | Production auth or custom callback | Empty | Shared bearer token for private development integrations. |
| `APP_CORS_ORIGINS` | For browser clients | Empty | Comma-separated exact frontend origins. |
| `APP_BASE_URL` | No | `http://localhost:8000` | Application API identity/configuration value; not the OpenAI URL. |
| `PYREALTIME_ALLOW_ANONYMOUS` | No | `false` | Allows unauthenticated API calls. Local prototypes only. |
| `PYREALTIME_MODEL` | No | `gpt-realtime-2.1-mini` | Realtime session model. |
| `PYREALTIME_VOICE` | No | `marin` | Realtime output voice. |
| `PYREALTIME_INSTRUCTIONS` | No | Concise assistant prompt | Initial Realtime instructions. |
| `PYREALTIME_REQUEST_TIMEOUT_SECONDS` | No | `20` | Realtime REST/session setup timeout. |
| `PYREALTIME_TOOL_MODEL` | No | `gpt-5-mini` | Responses API model for server-side tools. |
| `PYREALTIME_TOOL_TIMEOUT_SECONDS` | No | `120` | Timeout for searches and other hosted tools. |
| `PYREALTIME_IMAGE_MODEL` | No | `gpt-image-2.5-flare` | Image generation model. |
| `PYREALTIME_VECTOR_STORE_IDS` | No | Empty | Comma-separated OpenAI vector store IDs. Enables `file_search`. |
| `PYREALTIME_MAX_SDP_BYTES` | No | `1000000` | Maximum unified WebRTC SDP request body. |
| `PYREALTIME_MAX_TOOL_REQUEST_BYTES` | No | `64000` | Maximum JSON body for one tool call. |
| `PYREALTIME_SESSION_RATE_LIMIT` | No | `10` | Session/token requests per principal per window; `0` disables. |
| `PYREALTIME_TOOL_RATE_LIMIT` | No | `60` | Tool calls per principal per window; `0` disables. |
| `PYREALTIME_FILE_RATE_LIMIT` | No | `10` | File preparations per principal per window; `0` disables. |
| `PYREALTIME_RATE_LIMIT_WINDOW_SECONDS` | No | `60` | Window used by all built-in rate limits. |
| `PYREALTIME_REQUEST_ID_HEADER` | No | `X-Request-ID` | Correlation header accepted and returned by the API. |
| `PYREALTIME_JSON_LOGS` | No | `true` | Emits structured request logs without headers or bodies. |

Never place `OPENAI_API_KEY` in browser code, `VITE_*` variables, local storage, or a public repository.

## 6. Authentication modes

Every endpoint except `/v1/health` resolves a `Principal`.

### Shared bearer token

Set `APP_API_KEY`, then send:

```http
Authorization: Bearer local-development-token
```

This mode maps every valid request to the same principal and is intended for development or private single-tenant integrations.

### Application authentication callback

Use a callback for production:

```python
from fastapi import HTTPException, Request
from pyrealtime import Principal, ServerSettings, ToolRegistry
from pyrealtime.api import create_app


async def authenticate(request: Request) -> Principal:
    token = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    user = await verify_your_jwt_and_load_user(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid user session")
    return Principal(id=str(user.id), claims={"plan": user.plan})


settings = ServerSettings.from_env()
app = create_app(settings, tools=ToolRegistry(), authenticate=authenticate)
```

The callback must verify identity. Model-generated tool arguments are never authorization evidence. Tool handlers must derive ownership and permissions from `principal`.

### Reference JWT adapters and host policy hooks

Install the `auth` extra and use `JWTAuthenticator` with either a shared HS256 secret or a JWKS URL. Always configure an explicit algorithm, audience, and issuer. `HostHooks.authorize` receives a typed `AuthorizationRequest` before session creation, tool execution, or file preparation. `HostHooks.on_lifecycle` observes started/completed events without receiving prompt, token, or file content.

```python
from pyrealtime import HostHooks, JWTAuthenticator

authenticate = JWTAuthenticator(
    algorithms=("RS256",),
    jwks_url="https://identity.example.com/.well-known/jwks.json",
    audience="realtime-api",
    issuer="https://identity.example.com/",
)

async def authorize(principal, request):
    if request.action == "tool.execute":
        return request.resource in principal.claims.get("allowed_tools", [])
    return True

app = create_app(settings, authenticate=authenticate, host=HostHooks(authorize=authorize))
```

See `examples/jwt_host_server.py` for a complete second host with its own JWT, authorization rule, and tool. Run it with `uvicorn examples.jwt_host_server:build_app --factory` after setting `OPENAI_API_KEY`, `EXAMPLE_JWT_SECRET`, and CORS.

### Anonymous mode

`PYREALTIME_ALLOW_ANONYMOUS=true` exists only for controlled local prototypes. It maps all requests to one anonymous principal.

## 7. HTTP API contract

All protected examples below may require:

```http
Authorization: Bearer <application-token-or-user-JWT>
```

### `GET /v1/health`

No authentication. Returns server health only; it does not validate the OpenAI key.

### `POST /v1/realtime/session`

This is the path used by `pyrealtime-web`. The browser sends its SDP offer to PyRealtime, and PyRealtime sends the configured session plus SDP to OpenAI using the standard server key.

Request:

```http
Content-Type: application/sdp

v=0
...browser SDP offer...
```

Successful response:

```http
Content-Type: application/sdp

v=0
...OpenAI SDP answer...
```

Use this unified path when you want the browser to talk only to your application backend during session creation.

### `POST /v1/realtime/token`

Creates a short-lived Realtime client secret and returns OpenAI's JSON response. Use it only with a frontend that implements the ephemeral-token connection flow. The reference frontend currently uses `/v1/realtime/session`, not this endpoint.

Both WebRTC approaches are supported by the official OpenAI documentation: [unified interface and ephemeral token](https://developers.openai.com/api/docs/guides/voice-webrtc).

### `POST /v1/tools/{tool_name}`

Executes a registered backend tool for the authenticated principal.

Request:

```bash
curl -X POST http://127.0.0.1:8000/v1/tools/backend_openai_call \
  -H "Authorization: Bearer local-development-token" \
  -H "Content-Type: application/json" \
  -d '{"input":"Invoice total: 42.50","instructions":"Extract the total as JSON."}'
```

The JSON request body is the tool arguments object. The response is the handler's JSON-compatible result.

Possible statuses:

- `200`: tool completed.
- `400`: handler rejected invalid arguments.
- `401`: application authentication failed.
- `404`: tool is not registered.
- `413`: request exceeds the configured body limit.
- `429`: the principal exceeded the configured rate limit; honor `Retry-After`.
- `502`: OpenAI or another upstream service rejected or timed out.

Every response includes `X-Request-ID` (or the configured header). A safe caller-provided ID is preserved; otherwise PyRealtime generates one.

### `POST /v1/files/prepare`

Available only when `create_app(..., attachments=AttachmentProcessor())` is used.

Headers:

```http
Content-Type: <actual file MIME type>
X-Filename: <URL-encoded filename>
Authorization: Bearer <token>
```

The raw file bytes are the request body. The response is one of:

- `kind: "image"` with a normalized `data_url`.
- `kind: "text"` with extracted `chunks` and a `truncated` flag.
- `kind: "notice"` with an honest unsupported-format message.

Default limits are defined by `AttachmentPolicy`: 25 MB input, 120,000 extracted characters, 8,000 characters per chunk, 1,024-pixel image dimensions, 250 document pages, and 100,000 spreadsheet cells.

Preparation is stateless by default. Pass `attachment_store=` with an object implementing `async save(principal_id, attachment)` to add host-controlled persistence; its returned reference appears under `storage`.

## 8. Creating a complete API application

```python
from pyrealtime import (
    AttachmentProcessor,
    OpenAIHostedTools,
    Principal,
    ServerSettings,
    ToolRegistry,
)
from pyrealtime.api import create_app

settings = ServerSettings.from_env()
tools = ToolRegistry()

OpenAIHostedTools(
    api_key=settings.openai_api_key,
    response_model=settings.tool_model,
    image_model=settings.image_model,
    vector_store_ids=settings.vector_store_ids,
    timeout=settings.tool_timeout_seconds,
).register(tools)


@tools.tool(
    name="task_create",
    description="Create a task for the authenticated user.",
    parameters={
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 200}
        },
        "required": ["title"],
        "additionalProperties": False,
    },
)
async def task_create(arguments, principal: Principal):
    title = str(arguments.get("title", "")).strip()
    if not title:
        raise ValueError("title is required")
    task = await your_database.create_task(owner_id=principal.id, title=title)
    return {"ok": True, "task_id": str(task.id), "title": task.title}


app = create_app(
    settings,
    tools=tools,
    attachments=AttachmentProcessor(),
)
```

`create_app` also accepts `host=HostHooks(...)`, a distributed `rate_limiter=`, `attachment_store=`, and `usage_sink=`. Defaults are safe for a single process: an in-memory per-principal limiter, no attachment persistence, and a no-op usage sink. Multi-instance deployments should supply a Redis/database-backed limiter. Billing rules intentionally belong in the host's `UsageSink`, not the core library.

Run it with:

```bash
python -m uvicorn your_module:app --host 0.0.0.0 --port 8000
```

## 9. Built-in server tools

`OpenAIHostedTools.register()` adds these function schemas to the Realtime session and executes them through PyRealtime:

| Tool | Arguments | Availability | Result |
| --- | --- | --- | --- |
| `web_search` | `{ "query": string }` | Always | `output_text`, citations, response ID |
| `backend_openai_call` | `{ "input": string, "instructions": string }` | Always | Server-side Responses API text result |
| `generate_image` | `prompt` plus optional size, quality, format, background | Always | Browser-ready image data URI |
| `file_search` | `{ "query": string }` | Only with vector store IDs | Search answer and file citations |

`backend_openai_call` is the single backend model call equivalent of the former plugin workflow. It is separate from the Realtime conversation.

Web search uses OpenAI's Responses API hosted web search. File search uses OpenAI's hosted file search and requires a previously created vector store containing uploaded files. See the official [web search](https://developers.openai.com/api/docs/guides/tools-web-search) and [file search](https://developers.openai.com/api/docs/guides/tools-file-search) guides.

The browser must display web citations as visible, clickable links when presenting sourced search results.

## 10. Creating a file-search knowledge base

PyRealtime consumes existing OpenAI vector store IDs; vector-store creation/upload administration intentionally remains an optional host service.

Required sequence:

1. Upload files to OpenAI using the Files API.
2. Create a vector store.
3. Add the uploaded files to that vector store.
4. Wait until processing completes.
5. Put the vector store ID in `PYREALTIME_VECTOR_STORE_IDS`.
6. Restart the backend so the `file_search` schema is registered.

If `PYREALTIME_VECTOR_STORE_IDS` is empty, `file_search` is intentionally absent from the Realtime session.

Do not accept arbitrary vector store IDs from an untrusted browser in a multi-user application. Resolve allowed stores server-side from the authenticated `Principal`.

For multi-tenant deployments, pass `vector_store_resolver=` to `OpenAIHostedTools`. The sync or async resolver receives the authenticated `Principal`; `file_search` fails closed when it returns no authorized stores.

## 11. Tool execution rules

- Tool names must match `^[a-z0-9_.-]{1,64}$`.
- Parameters must be a JSON Schema object.
- Set `additionalProperties: false` unless unknown fields are intentionally supported.
- Validate arguments again inside the handler.
- Derive user identity and ownership from `Principal`.
- Return small JSON-compatible results.
- Do not return secrets, raw credentials, database connections, or large binary data to the Realtime channel.
- Device-local effects such as avatar animation and browser navigation belong in the frontend.
- Business operations, database access, authorization, web search, file search, and model calls belong on the server.

## 12. Direct library use without FastAPI

```python
import asyncio
from pyrealtime import OpenAIRealtimeGateway, RealtimeSessionConfig


async def main():
    gateway = OpenAIRealtimeGateway(api_key="sk-server-only")
    try:
        config = RealtimeSessionConfig(
            model="gpt-realtime-2.1-mini",
            voice="marin",
            instructions="Be concise and helpful.",
            vad_threshold=0.5,
        )
        secret = await gateway.create_client_secret(
            config,
            safety_identifier="stable-hashed-internal-user-id",
        )
        print(secret["value"])
    finally:
        await gateway.aclose()


asyncio.run(main())
```

Use the FastAPI factory when possible; it already applies authentication, authorization hooks, CORS, safety identifiers, error mapping, rate/body limits, request IDs, structured logs, tool registration, and attachment limits.

## 13. Production checklist

- Keep `OPENAI_API_KEY` only in a server secret manager.
- Replace shared `APP_API_KEY` authentication with verified user sessions or JWTs.
- Return a stable, non-secret internal user ID from the authentication callback.
- Configure exact HTTPS frontend origins in `APP_CORS_ORIGINS`.
- Serve both frontend and API over HTTPS.
- Enforce authorization inside every state-changing tool.
- Tune PyRealtime body/rate limits and enforce a second outer limit at the reverse proxy.
- Replace the process-local limiter when running more than one API instance.
- Forward `X-Request-ID`; built-in JSON logs omit headers, prompts, tokens, arguments, and file contents.
- Resolve vector stores and other private resources from the principal.
- Pin and review dependency versions.
- Run `python -m pytest` before deployment.
- Review the MIT license and compatibility policy for the intended deployment.

## 14. Troubleshooting

### `OPENAI_API_KEY` appears empty

Creating `.env` does not load it automatically. Export the variable in the process environment or load it in your host application before importing the example server.

### `401 Invalid application token`

The browser token does not match `APP_API_KEY`, or your custom authenticator rejected it. Do not enter the OpenAI key in the frontend token field.

### `502 OpenAI rejected the WebRTC session request`

Check the backend response detail and confirm:

- The OpenAI key is valid.
- The project can use `PYREALTIME_MODEL`.
- Project quota and rate limits are available.
- The configured session fields are supported by that model.

### Web search times out

Search has its own timeout. Increase `PYREALTIME_TOOL_TIMEOUT_SECONDS` if necessary. The default is 120 seconds.

### `file_search` is missing

Set `PYREALTIME_VECTOR_STORE_IDS`, then restart the backend and reconnect the Realtime session. Tool schemas are loaded when the session is created.

### Browser CORS failure

Add the exact frontend origin, including scheme and port, to `APP_CORS_ORIGINS`, then restart the backend.

### Port 8000 is already in use

Stop the process that owns the port or start Uvicorn on another port and configure the frontend to use that URL.

## 15. Tests and verification

```bash
python -m pip install -e ".[api,auth,files,dev]"
python -m pytest
```

An LLM making changes must also:

1. Read `instructions.md` and `ARCHITECTURE.md`.
2. Preserve the server/frontend boundary.
3. Add or update tests for changed behavior.
4. Run the complete Python test suite.
5. Update this guide when public configuration, endpoints, schemas, defaults, or setup commands change.

## 16. Optional capability boundaries and known limitations

- The release workflow always creates validated wheel/sdist GitHub assets. PyPI publishing of `pyrealtime-ai` begins after the repository owner enables the documented trusted publisher and `PYPI_PUBLISH_ENABLED` variable.
- The default limiter and attachment preparation are process-local/stateless. Production hosts can replace them through `RateLimiter` and `AttachmentStore` protocols.
- Usage events are emitted through `UsageSink`; price tables, quotas, invoicing, and plan policy remain application-owned.
- Vector-store creation/upload management remains an optional host administration service. Runtime search authorization is supported by `vector_store_resolver`.
- Initial session policy is server-controlled. The reusable browser client exposes `updateSession()` for supported live updates; OpenAI does not permit changing the voice after audio has already been emitted.
- PyRealtime does not provide login UI, tenant/company rules, databases, or browser rendering. Those are explicit host/client boundaries, not implicit demo assumptions.
