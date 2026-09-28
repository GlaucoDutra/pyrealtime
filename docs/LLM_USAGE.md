# PyRealtime 0.3.0 complete usage guide

This is the canonical reference for humans and language models integrating `pyrealtime-ai`. The README is the quick start; when they differ, this file defines the intended public contract for release `v0.3.0`. Short client/framework recipes are in [QUICKSTARTS.md](QUICKSTARTS.md).

## 1. Definition of drop-in

A new, unrelated application can use PyRealtime without cloning its source or using another repository. The host must provide only:

1. Python 3.10, 3.11, 3.12, or 3.13.
2. The pinned wheel and appropriate extras.
3. A server-side OpenAI API key when using the default OpenAI chat or Realtime adapters.
4. Authentication: a local shared key, a callback returning `Principal`, or `JWTAuthenticator`.
5. Any application tools and their authorization rules.

The host retains user accounts, databases, tenant/company policy, billing, quotas, UI, and deployment. PyRealtime does not require Supabase or any other database/identity vendor.

## 2. Installation and package identity

- Distribution: `pyrealtime-ai`
- Import: `pyrealtime`
- Current release: `0.3.0`
- Supported Python: 3.10–3.13
- License: MIT
- PyPI status: pending; no matching `pyrealtime-ai` distribution was available when 0.3.0 was prepared.
- Supported installation today: immutable GitHub release artifact.

```bash
python -m venv .venv
python -m pip install "pyrealtime-ai[api,auth] @ https://github.com/GlaucoDutra/pyrealtime/releases/download/v0.3.0/pyrealtime_ai-0.3.0-py3-none-any.whl"
```

Extras:

| Extra | Adds | Use when |
| --- | --- | --- |
| `api` | FastAPI and Uvicorn | Exposing or mounting the HTTP API |
| `auth` | PyJWT and cryptography | Validating HMAC or JWKS JWTs |
| `files` | PDF, Office, spreadsheet, and image parsers | Enabling `/v1/files/prepare` |
| `dev` | Tests, build, and package inspection | Contributing from a source checkout |

Do not use `pip install pyrealtime`: that is a different, older project. Do not claim PyPI availability until `pip index versions pyrealtime-ai` returns the released version.

## 3. Adoption commands

### Starter generator

```bash
pyrealtime init my-ai-backend
```

The command accepts only a new or empty directory and never overwrites an existing project. It creates:

- `app.py` with FastAPI, shared-key development authentication, `HostHooks`, and one tool.
- `.env.example` with explicit demo mode and server-only credential placeholders.
- A release-pinned `requirements.txt` that does not require a source checkout.
- A small README and `.gitignore`.

The generated host starts with `PYREALTIME_DEMO=true`, fake chat, and no Realtime routes. Set it to `false` and configure a server-side OpenAI key to enable the real default adapters. Replace shared-key authentication and the permissive example authorization hook before public multi-user deployment.

### Setup doctor

Offline configuration/dependency check:

```bash
pyrealtime doctor --no-network
```

Running API, CORS, and OpenAI model-access check:

```bash
pyrealtime doctor --api-url http://127.0.0.1:8000/ai --origin http://localhost:3000
```

The OpenAI connectivity check retrieves model metadata and does not create a model response. The doctor reports only statuses and generic remediation text: it never prints API keys, bearer tokens, prompts, response bodies, or configuration values. Use `--skip-openai` to omit OpenAI connectivity and `--strict` to make warnings produce a nonzero exit code. `PYREALTIME_API_URL` and `PYREALTIME_DOCTOR_ORIGIN` are CLI defaults for the matching flags.

### No-key demo

```bash
pyrealtime demo
```

This binds to `127.0.0.1:8000`, uses bearer token `local-demo-token` unless `APP_API_KEY` is already set, and never contacts OpenAI. Every chat response contains `DEMO MODE`, usage is `null`, and Realtime routes are absent. It also exposes the direct `get_status` tool. `DemoChatBackend` and `create_demo_app` are public for tests and onboarding, but they are not production AI implementations.

## 4. Smallest standalone integration

```python
from pyrealtime import Principal, ServerSettings, ToolRegistry
from pyrealtime.api import create_app

settings = ServerSettings(
    openai_api_key="server-secret",
    app_api_key="local-app-token",
    cors_origins=("http://localhost:3000",),
)
tools = ToolRegistry()

@tools.tool(
    name="get_status",
    description="Return the current service status.",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
async def get_status(arguments, principal: Principal):
    return {"status": "ready", "principal_id": principal.id}

app = create_app(settings, tools=tools)
```

Run:

```bash
uvicorn your_module:app --host 127.0.0.1 --port 8000
```

`APP_API_KEY` maps every valid request to the same development principal. It is suitable for local or private single-identity testing, not public multi-user login.

## 5. Mounting into an existing ASGI application

`mount_py_realtime` mounts a self-contained FastAPI sub-application. This preserves request IDs, CORS, error handlers, docs, and limits without changing the host's middleware.

```python
from fastapi import FastAPI, HTTPException, Request
from pyrealtime import Principal, ServerSettings, ToolRegistry
from pyrealtime.api import mount_py_realtime

app = FastAPI()
tools = ToolRegistry()

async def authenticate(request: Request) -> Principal:
    session = await your_identity_service.verify(request.headers.get("authorization", ""))
    if session is None:
        raise HTTPException(status_code=401, detail="Invalid session")
    return Principal(id=str(session.user_id), claims={"roles": session.roles})

pyrealtime_app = mount_py_realtime(
    app,
    ServerSettings.from_env(),
    path="/ai",
    tools=tools,
    authenticate=authenticate,
)
```

The resulting API is `/ai/v1/...` and its OpenAPI UI is `/ai/docs`. The path must be a non-root absolute path. Use `create_app` when PyRealtime itself is the standalone ASGI application.

Chat and Realtime are enabled by default. Set `enable_chat=False` or `enable_realtime=False` to omit either route group. A host using a custom `ChatBackend` with `enable_realtime=False` does not need an OpenAI key; direct tools also work with both provider capabilities disabled.

Default network adapters create short-lived HTTP clients and are safe in a mounted child application. An injected HTTP client, gateway, or backend is host-owned and must be closed by the host lifespan.

## 6. Authentication, authorization, and lifecycle

Every route except health resolves a `Principal` and fails closed:

- Custom `authenticate(request)` callback: recommended for an existing app.
- `JWTAuthenticator`: validates an explicit algorithm, audience, issuer, and either a shared secret or JWKS URL.
- `APP_API_KEY`: development/private integration fallback.
- Anonymous: disabled unless `PYREALTIME_ALLOW_ANONYMOUS=true`; use only in controlled prototypes.
- No configured mode: protected routes return `503`.

```python
from pyrealtime import HostHooks, JWTAuthenticator

authenticate = JWTAuthenticator(
    algorithms=("RS256",),
    jwks_url="https://identity.example.com/.well-known/jwks.json",
    audience="my-api",
    issuer="https://identity.example.com/",
)

async def authorize(principal, request):
    if request.action == "tool.execute":
        return request.resource in principal.claims.get("allowed_tools", [])
    return True

hooks = HostHooks(authorize=authorize, on_lifecycle=record_safe_event)
```

Authorization actions are:

| Action | Resource |
| --- | --- |
| `chat.complete` | `None` |
| `realtime.session` | `None` |
| `tool.execute` | Tool name |
| `file.prepare` | `None` |

Chat-triggered tools are authorized again with `tool.execute` immediately before execution. Model arguments never establish authorization.

Lifecycle events contain request ID, principal ID, event name, and small operational metadata—not prompts, tokens, tool arguments/results, or file contents.

## 7. Chat API

### Request

`POST /v1/chat`, `Content-Type: application/json`:

```json
{
  "message": "What is my service status?",
  "history": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "How can I help?"}
  ]
}
```

The request is provider-neutral. Roles are `user` or `assistant`; system/developer instructions are controlled by the server. Clients send bounded replayable history, not provider response IDs or raw provider output items.

### Response

```json
{
  "message": {"role": "assistant", "content": "The service is ready."},
  "tool_calls": [
    {
      "id": "call_123",
      "name": "get_status",
      "arguments": {},
      "status": "completed",
      "result": {"status": "ready"},
      "error": null
    }
  ],
  "usage": {"input_tokens": 42, "output_tokens": 12, "total_tokens": 54}
}
```

`usage` may be `null` for a custom provider that does not report counts. Tool failures use `status: "failed"` and a bounded, non-sensitive error code such as `tool_timeout`; raw exceptions are not returned.

### Error envelope

Chat errors use one stable envelope and include the same request ID returned in the response header:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "message exceeds the configured character limit",
    "request_id": "7f5..."
  }
}
```

Expected codes include `unauthorized`, `forbidden`, `invalid_request`, `request_too_large`, `rate_limited`, `provider_error`, `provider_timeout`, `chat_timeout`, and `tool_round_limit`. Honor `Retry-After` on `429`.

The default `OpenAIResponsesChatBackend` uses the Responses API internally, sends `store: false`, executes only registered application tools, and runs a bounded tool loop. A host can inject any object implementing `ChatBackend`; the HTTP schema does not change.

Python consumers can use `await AppClient(...).chat(message, history=...)`; it validates both the request and provider-neutral response with these same public models.

## 8. Other HTTP routes

| Route | Purpose |
| --- | --- |
| `GET /v1/health` | Public process health and package version; does not validate provider credentials |
| `POST /v1/realtime/token` | Short-lived Realtime client secret |
| `POST /v1/realtime/session` | Unified SDP exchange for browser WebRTC |
| `POST /v1/tools/{tool_name}` | Direct execution of one registered tool |
| `POST /v1/files/prepare` | Optional authenticated attachment preparation |

Realtime routes expose the provider's SDP/token transport because those are protocol endpoints. `/v1/chat` deliberately does not expose provider response objects.

## 9. Tools

Register only server-owned schemas:

```python
tools = ToolRegistry()

@tools.tool(
    name="lookup_order",
    description="Look up an order owned by the authenticated user.",
    parameters={
        "type": "object",
        "properties": {"order_id": {"type": "string"}},
        "required": ["order_id"],
        "additionalProperties": False,
    },
)
async def lookup_order(arguments, principal):
    return await database.orders.for_owner(principal.id, arguments["order_id"])
```

The direct tool route and chat orchestration both enforce `PYREALTIME_TOOL_TIMEOUT_SECONDS`. Chat additionally bounds tool rounds and serialized result size. Unknown, rejected, oversized, failed, or timed-out chat tools return safe error codes to the model and caller.

`OpenAIHostedTools` remains optional for hosted web search, file search, image generation, and a private model call. File search consumes host-authorized vector store IDs; vector-store creation/upload administration remains outside the core.

## 10. Files and optional persistence

Install `files`, construct `AttachmentProcessor`, and pass it to `create_app`/`mount_py_realtime`. The request body is raw bytes with `Content-Type` and URL-encoded `X-Filename`.

Default preparation limits: 25 MB input, 120,000 extracted characters, 8,000-character chunks, 1,024-pixel normalized images, 250 pages/slides, and 100,000 spreadsheet cells.

Processing is stateless by default. `AttachmentStore.save(principal_id, prepared_attachment)` is the vendor-neutral persistence extension. The host chooses filesystem, object storage, database, retention, encryption, and deletion policy.

## 11. Guardrails and operational defaults

| Guardrail | Default | Scope |
| --- | --- | --- |
| Chat request body | 256,000 bytes | Per request |
| Current chat message | 32,000 characters | Per request |
| Chat history | 20 messages / 120,000 characters | Per request |
| Chat tool rounds | 4 | Per response |
| Chat tool result | 32,000 serialized characters | Per call |
| Chat output | 2,048 tokens | Provider request |
| Chat timeout | 120 seconds | Whole completion, including provider rounds and tool calls |
| Tool timeout | 120 seconds | Direct and chat tool execution |
| Session rate | 10 / 60 seconds | Per principal |
| Chat rate | 30 / 60 seconds | Per principal |
| Tool rate | 60 / 60 seconds | Per principal |
| File rate | 10 / 60 seconds | Per principal |

Set a rate value to `0` to disable that built-in limit. `InMemoryRateLimiter` is process-local and resets on restart; multi-instance deployments must inject a shared `RateLimiter`. `NullUsageSink` records nothing; inject `UsageSink` for host-owned metering/billing. Neither protocol requires a vendor.

Request logs are structured JSON by default. They contain timestamp, method, path, status, duration, and request ID. Headers, bearer tokens, prompts, history, tool arguments/results, and file content are not logged. `redact()` recursively removes common secret-bearing keys from host-added structured fields.

CORS is disabled unless exact origins are configured. Configure HTTPS origins explicitly; a wildcard is not appropriate for credentialed production browser calls. Enforce outer body/rate limits at the proxy as defense in depth.

## 12. Environment variables

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENAI_API_KEY` | Empty | Server-only provider key |
| `APP_API_KEY` | Empty | Shared local/private bearer key |
| `APP_BASE_URL` | `http://localhost:8000` | Host API identity/config value |
| `APP_CORS_ORIGINS` | Empty | Comma-separated exact browser origins |
| `PYREALTIME_ALLOW_ANONYMOUS` | `false` | Explicit prototype-only anonymous mode |
| `PYREALTIME_MODEL` | `gpt-realtime-2.1-mini` | Realtime model |
| `PYREALTIME_VOICE` | `marin` | Realtime voice |
| `PYREALTIME_INSTRUCTIONS` | Concise Realtime prompt | Server-controlled Realtime instructions |
| `PYREALTIME_CHAT_MODEL` | `gpt-5-mini` | Default chat model |
| `PYREALTIME_CHAT_INSTRUCTIONS` | Concise assistant prompt | Server-controlled chat instructions |
| `PYREALTIME_CHAT_TIMEOUT_SECONDS` | `120` | Overall chat timeout, including provider rounds and tool calls |
| `PYREALTIME_CHAT_MAX_OUTPUT_TOKENS` | `2048` | Chat output cap |
| `PYREALTIME_MAX_CHAT_REQUEST_BYTES` | `256000` | Chat JSON body cap |
| `PYREALTIME_MAX_CHAT_MESSAGE_CHARS` | `32000` | Current-message cap |
| `PYREALTIME_MAX_CHAT_HISTORY_MESSAGES` | `20` | History item cap |
| `PYREALTIME_MAX_CHAT_HISTORY_CHARS` | `120000` | Aggregate history cap |
| `PYREALTIME_MAX_CHAT_TOOL_ROUNDS` | `4` | Tool loop cap |
| `PYREALTIME_MAX_CHAT_TOOL_RESULT_CHARS` | `32000` | Serialized tool result cap |
| `PYREALTIME_REQUEST_TIMEOUT_SECONDS` | `20` | Realtime setup timeout |
| `PYREALTIME_TOOL_TIMEOUT_SECONDS` | `120` | Tool execution/hosted-tool timeout |
| `PYREALTIME_MAX_SDP_BYTES` | `1000000` | SDP request cap |
| `PYREALTIME_MAX_TOOL_REQUEST_BYTES` | `64000` | Direct tool JSON cap |
| `PYREALTIME_SESSION_RATE_LIMIT` | `10` | Sessions per rate window |
| `PYREALTIME_CHAT_RATE_LIMIT` | `30` | Chats per rate window |
| `PYREALTIME_TOOL_RATE_LIMIT` | `60` | Direct tools per rate window |
| `PYREALTIME_FILE_RATE_LIMIT` | `10` | Files per rate window |
| `PYREALTIME_RATE_LIMIT_WINDOW_SECONDS` | `60` | Process-local limiter window |
| `PYREALTIME_REQUEST_ID_HEADER` | `X-Request-ID` | Correlation header |
| `PYREALTIME_JSON_LOGS` | `true` | Safe structured access logging |
| `PYREALTIME_TOOL_MODEL` | `gpt-5-mini` | Hosted backend tool model |
| `PYREALTIME_IMAGE_MODEL` | `gpt-image-2.5-flare` | Hosted image model |
| `PYREALTIME_VECTOR_STORE_IDS` | Empty | Static hosted file-search stores |

`ServerSettings.from_env()` reads the process environment; it does not load `.env` files. Never put `OPENAI_API_KEY`, administrative tokens, database credentials, or private vector store IDs in public frontend variables.

## 13. Installed independent example

The release wheel installs `pyrealtime-example`. It uses only public APIs, mounts PyRealtime at `/ai`, and registers one `greet` tool.

Local authentication:

```bash
OPENAI_API_KEY=sk-server-only APP_API_KEY=local-token pyrealtime-example
```

Production-style JWT verification:

```bash
OPENAI_API_KEY=sk-server-only \
EXAMPLE_JWKS_URL=https://identity.example.com/.well-known/jwks.json \
EXAMPLE_JWT_AUDIENCE=my-api \
EXAMPLE_JWT_ISSUER=https://identity.example.com/ \
pyrealtime-example
```

The JWT needs `pyrealtime:tools` in its space-delimited `scope` claim for tool execution. Provider secrets remain server-side.

## 14. Verification and release

Contributor verification:

```bash
python -m pip install -e ".[api,auth,dev,files]"
python -m pytest
python -m build
python -m twine check dist/*
```

CI runs the suite and a wheel-only consumer smoke test on Python 3.10–3.13. The smoke test imports only public APIs, mounts the installed example, and exercises health, authentication, chat, a tool, validation errors, and rate limits. CI also lists wheel and source-archive contents.

Release steps are in `RELEASING.md`. A release is complete only when the tag workflow succeeds and the GitHub release contains both the `.whl` and `.tar.gz`. PyPI remains pending until both trusted-publisher configuration and an actual installation check succeed.

## 15. Explicit non-goals and optional capabilities

- User/account/tenant storage and login UI.
- Company-specific authorization rules.
- Billing prices, invoices, and plan enforcement; use `UsageSink`.
- A required database, cache, queue, or object-storage vendor.
- Vector-store creation/upload administration.
- Durable conversation storage; clients or hosts may persist the neutral message schema.
- Frontend UI, microphone capture, WebRTC rendering, or avatar behavior.

The default chat path is stateless: the caller supplies bounded history. This avoids hidden provider conversation state and keeps persistence a host decision.
