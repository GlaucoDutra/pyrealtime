# PyRealtime

`pyrealtime` is a framework-neutral Python backend library for a public browser frontend using OpenAI Realtime over WebRTC.

The backend keeps the standard OpenAI API key private, creates short-lived client secrets, executes application tools, and exposes an optional FastAPI surface. The browser continues to own microphone capture, remote audio playback, the WebRTC peer connection, and the Three.js avatar.

## Install

```bash
python -m pip install -e ".[api,dev,files]"
```

Copy `.env.example` into your deployment environment and set `OPENAI_API_KEY`. Never expose that value in frontend code.

## Core library

```python
import asyncio

from pyrealtime import OpenAIRealtimeGateway, RealtimeSessionConfig


async def main() -> None:
    gateway = OpenAIRealtimeGateway(api_key="sk-server-only")
    config = RealtimeSessionConfig(
        model="gpt-realtime-2.1-mini",
        voice="marin",
        instructions="You are a concise work assistant.",
    )

    secret = await gateway.create_client_secret(
        config,
        safety_identifier="sha256-of-your-internal-user-id",
    )
    print(secret["value"])
    await gateway.aclose()


asyncio.run(main())
```

## FastAPI application

`examples/api_server.py` creates these endpoints:

- `GET /v1/health`
- `POST /v1/realtime/token`
- `POST /v1/realtime/session` (optional unified SDP proxy)
- `POST /v1/tools/{tool_name}`
- `POST /v1/files/prepare` (when an `AttachmentProcessor` is supplied)

Run it with:

```bash
uvicorn examples.api_server:app --reload
```

The frontend should be configured with the API's public origin:

```javascript
const appBaseUrl = "https://api.example.com";

const tokenResponse = await fetch(`${appBaseUrl}/v1/realtime/token`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${userSessionToken}`,
  },
});

const token = await tokenResponse.json();
```

`app_base_url` always means your application API. It is not the OpenAI endpoint and it is not tied to any hosting platform.

The default model is `gpt-realtime-2.1-mini`, selected for substantially lower speech-to-speech cost while retaining WebRTC and function calling. Set `PYREALTIME_MODEL=gpt-realtime-2.1` when a deployment needs the larger model's stronger instruction following and tool use.

## Register tools

```python
from pyrealtime import ToolRegistry

tools = ToolRegistry()


@tools.tool(
    name="task_create",
    description="Create a task for the authenticated user.",
    parameters={
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
        "additionalProperties": False,
    },
)
async def create_task(arguments, principal):
    return {
        "ok": True,
        "task": {
            "title": arguments["title"],
            "owner_id": principal.id,
        },
    }
```

Tool arguments are model-generated input, not authorization. Every handler must derive ownership and permissions from the authenticated `Principal`.

## Application authentication

`create_app` accepts a custom asynchronous authentication callback. In production, use it to verify your application's user session or JWT and return a stable internal user ID. If no callback is supplied, `APP_API_KEY` enables a simple bearer-key mode intended for private integrations and development.

Anonymous access is disabled by default. It must be enabled explicitly with `PYREALTIME_ALLOW_ANONYMOUS=true`.

Set `APP_CORS_ORIGINS` to a comma-separated allowlist of frontend origins. Do not use a wildcard with credentialed production requests.

## Reusable attachment processing

Install the `files` extra and pass an `AttachmentProcessor` to `create_app`. The authenticated `POST /v1/files/prepare` endpoint accepts the raw file body, its MIME type in `Content-Type`, and its URL-encoded name in `X-Filename`.

PyRealtime validates limits and returns a stable prepared-attachment model. It extracts and chunks text and source files, PDF, XLSX/XLSM, DOCX, and PPTX content; it also normalizes images for a Realtime image message. Processing is stateless and does not persist uploads.

```python
from pyrealtime import AttachmentProcessor
from pyrealtime.api import create_app

app = create_app(settings, attachments=AttachmentProcessor())
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the permanent boundary between reusable library behavior and client-specific code.

## Frontend boundary

The public frontend may contain WebRTC, avatar, and UI code. It must not contain:

- Standard OpenAI API keys
- Database credentials
- Administrative application tokens
- Authorization decisions

The server should derive `OpenAI-Safety-Identifier` from an authenticated internal user identifier. This library hashes the principal ID before sending it to OpenAI.

## Tests

```bash
pytest
```
