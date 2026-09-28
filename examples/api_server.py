"""Minimal application API. Replace the demo tool and authentication before production."""

from pyrealtime import AttachmentProcessor, JevClient, JevTools, OpenAIHostedTools, Principal, ServerSettings, ToolRegistry
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
if settings.typesafe_api_key:
    JevTools(JevClient(
        api_key=settings.typesafe_api_key,
        model=settings.jev_model,
        timeout=settings.jev_timeout_seconds,
        limits=settings.jev_limits(),
    )).register(tools)


@tools.tool(
    name="echo",
    description="Echo text through the application backend.",
    parameters={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    },
)
async def echo(arguments, principal: Principal):
    return {
        "ok": True,
        "text": str(arguments.get("text", "")),
        "principal_id": principal.id,
    }


app = create_app(settings, tools=tools, attachments=AttachmentProcessor())
