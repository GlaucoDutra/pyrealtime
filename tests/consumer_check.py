"""Run with a fresh interpreter that has only the built wheel installed."""

from fastapi.testclient import TestClient

from pyrealtime import (
    ChatMessage,
    ChatResponse,
    ChatUsage,
    JevClient,
    JevTools,
    ServerSettings,
    ToolRegistry,
    generate_starter,
)
from pyrealtime.example_app import create_example_app


class FakeChatBackend:
    async def complete(self, request, *, principal, tools, authorize_tool):
        del tools, authorize_tool
        return ChatResponse(
            message=ChatMessage(role="assistant", content=f"Echo: {request.message}"),
            usage=ChatUsage(input_tokens=2, output_tokens=2, total_tokens=4),
        )


class FakeRealtimeGateway:
    async def create_client_secret(self, config, *, safety_identifier=None):
        return {"value": "test", "expires_at": 1}

    async def create_webrtc_call(self, sdp_offer, config, *, safety_identifier=None):
        return "answer"


def main() -> None:
    import tempfile
    from pathlib import Path

    jev_tools = ToolRegistry()
    JevTools(JevClient(api_key="consumer-test-key")).register(jev_tools)
    assert jev_tools.schemas()[0]["name"] == "jev_decide"

    settings = ServerSettings(
        openai_api_key="server-only-test-key",
        app_api_key="local-token",
        json_logs=False,
        max_chat_message_chars=12,
        chat_rate_limit=3,
    )
    app = create_example_app(
        settings=settings,
        chat_backend=FakeChatBackend(),
        gateway=FakeRealtimeGateway(),
    )
    headers = {"Authorization": "Bearer local-token"}
    with TestClient(app) as client:
        health = client.get("/ai/v1/health")
        unauthorized = client.post("/ai/v1/chat", json={"message": "hello"})
        chat = client.post("/ai/v1/chat", headers=headers, json={"message": "hello"})
        tool = client.post("/ai/v1/tools/greet", headers=headers, json={"name": "Ada"})
        invalid = client.post("/ai/v1/chat", headers=headers, json={"message": "x" * 13})
        second = client.post("/ai/v1/chat", headers=headers, json={"message": "again"})
        limited = client.post("/ai/v1/chat", headers=headers, json={"message": "again"})

    assert health.json() == {"status": "ok", "service": "pyrealtime", "version": "0.4.0"}
    assert unauthorized.status_code == 401 and unauthorized.json()["error"]["code"] == "unauthorized"
    assert chat.status_code == 200 and chat.json()["message"]["content"] == "Echo: hello"
    assert tool.json()["message"] == "Hello, Ada!"
    assert invalid.status_code == 400 and invalid.json()["error"]["code"] == "invalid_request"
    assert second.status_code == 200
    assert limited.status_code == 429 and limited.headers["retry-after"]
    starter = Path(tempfile.mkdtemp()) / "starter"
    generate_starter(starter)
    assert (starter / "app.py").is_file()
    assert "pyrealtime_ai-0.4.0" in (starter / "requirements.txt").read_text()


if __name__ == "__main__":
    main()
