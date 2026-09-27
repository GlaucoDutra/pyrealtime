import asyncio

from fastapi.testclient import TestClient

from pyrealtime import ChatMessage, ChatResponse, ChatUsage, AttachmentProcessor, HostHooks, Principal, ServerSettings, ToolRegistry
from pyrealtime.api import create_app
from pyrealtime.exceptions import UpstreamError


class FakeGateway:
    def __init__(self):
        self.safety_identifier = None
        self.config = None

    async def create_client_secret(self, config, *, safety_identifier=None):
        self.config = config
        self.safety_identifier = safety_identifier
        return {"value": "ek_test", "expires_at": 123}

    async def create_webrtc_call(self, sdp_offer, config, *, safety_identifier=None):
        self.config = config
        self.safety_identifier = safety_identifier
        return "answer-for:" + sdp_offer


class RejectingGateway(FakeGateway):
    async def create_client_secret(self, config, *, safety_identifier=None):
        raise UpstreamError(
            "OpenAI rejected the request",
            status_code=401,
            response_body='{"error":{"message":"Incorrect API key provided","code":"invalid_api_key"}}',
        )


class FakeChatBackend:
    def __init__(self):
        self.principal = None

    async def complete(self, request, *, principal, tools, authorize_tool):
        del tools, authorize_tool
        self.principal = principal
        return ChatResponse(
            message=ChatMessage(role="assistant", content=f"Reply to: {request.message}"),
            usage=ChatUsage(input_tokens=3, output_tokens=2, total_tokens=5),
        )


def settings(**overrides):
    values = {
        "openai_api_key": "sk-test",
        "app_api_key": "app-secret",
    }
    values.update(overrides)
    return ServerSettings(**values)


def test_health_is_public():
    app = create_app(settings(), gateway=FakeGateway())
    with TestClient(app) as client:
        response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_token_requires_application_authentication_and_hashes_principal():
    gateway = FakeGateway()
    app = create_app(settings(), gateway=gateway)
    with TestClient(app) as client:
        unauthorized = client.post("/v1/realtime/token")
        authorized = client.post(
            "/v1/realtime/token",
            headers={"Authorization": "Bearer app-secret"},
        )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["value"] == "ek_test"
    assert gateway.safety_identifier
    assert gateway.config.model == "gpt-realtime-2.1-mini"


def test_tool_uses_authenticated_principal():
    tools = ToolRegistry()

    @tools.tool(
        name="whoami",
        description="Return the authenticated identity.",
        parameters={"type": "object", "properties": {}},
    )
    def whoami(_, principal: Principal):
        return {"id": principal.id}

    app = create_app(settings(), tools=tools, gateway=FakeGateway())
    with TestClient(app) as client:
        response = client.post(
            "/v1/tools/whoami",
            headers={"Authorization": "Bearer app-secret"},
            json={},
        )

    assert response.status_code == 200
    assert response.json() == {"id": "app-api-key"}


def test_unified_session_proxy_accepts_sdp():
    gateway = FakeGateway()
    app = create_app(settings(), gateway=gateway)
    with TestClient(app) as client:
        response = client.post(
            "/v1/realtime/session",
            headers={
                "Authorization": "Bearer app-secret",
                "Content-Type": "application/sdp",
            },
            content="offer-sdp",
        )

    assert response.status_code == 200
    assert response.text == "answer-for:offer-sdp"
    assert response.headers["content-type"].startswith("application/sdp")


def test_file_preparation_is_authenticated_and_reusable():
    app = create_app(settings(), attachments=AttachmentProcessor(), gateway=FakeGateway())
    with TestClient(app) as client:
        unauthorized = client.post(
            "/v1/files/prepare",
            headers={"X-Filename": "notes.txt", "Content-Type": "text/plain"},
            content=b"hello",
        )
        prepared = client.post(
            "/v1/files/prepare",
            headers={
                "Authorization": "Bearer app-secret",
                "X-Filename": "folder%2Fnotes.txt",
                "Content-Type": "text/plain",
            },
            content=b"hello",
        )

    assert unauthorized.status_code == 401
    assert prepared.status_code == 200
    assert prepared.json()["filename"] == "notes.txt"
    assert prepared.json()["chunks"] == ["hello"]


def test_upstream_authentication_error_is_actionable_without_echoing_raw_body():
    app = create_app(settings(), gateway=RejectingGateway())
    with TestClient(app) as client:
        response = client.post(
            "/v1/realtime/token",
            headers={"Authorization": "Bearer app-secret"},
        )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "OpenAI rejected the API key. Configure a valid OpenAI project API key.",
        "upstream_status": 401,
        "upstream_code": "invalid_api_key",
    }


def test_request_ids_limits_and_authorization_hooks():
    seen = []

    async def authorize(principal, request):
        seen.append((principal.id, request.action, request.request_id))
        return request.resource != "blocked"

    tools = ToolRegistry()

    @tools.tool(name="allowed", description="Allowed", parameters={"type": "object"})
    def allowed(_, principal):
        return {"id": principal.id}

    @tools.tool(name="blocked", description="Blocked", parameters={"type": "object"})
    def blocked(_, principal):
        return {"id": principal.id}

    app = create_app(
        settings(tool_rate_limit=1),
        tools=tools,
        host=HostHooks(authorize=authorize),
        gateway=FakeGateway(),
    )
    headers = {"Authorization": "Bearer app-secret", "X-Request-ID": "test-request"}
    with TestClient(app) as client:
        first = client.post("/v1/tools/allowed", headers=headers, json={})
        limited = client.post("/v1/tools/allowed", headers=headers, json={})
        forbidden = client.post("/v1/tools/blocked", headers=headers, json={})

    assert first.status_code == 200
    assert first.headers["x-request-id"] == "test-request"
    assert limited.status_code == 429
    assert limited.headers["retry-after"]
    assert forbidden.status_code == 403
    assert seen[0] == ("app-api-key", "tool.execute", "test-request")


def test_tool_body_size_is_enforced_before_json_parsing():
    app = create_app(settings(max_tool_request_bytes=4), tools=ToolRegistry(), gateway=FakeGateway())
    with TestClient(app) as client:
        response = client.post(
            "/v1/tools/anything",
            headers={"Authorization": "Bearer app-secret", "Content-Type": "application/json"},
            content=b'{"long":true}',
        )
    assert response.status_code == 413


def test_attachment_store_and_lifecycle_are_optional_extensions():
    events = []

    class Store:
        async def save(self, principal_id, attachment):
            return {"id": f"{principal_id}:{attachment.filename}"}

    async def lifecycle(event):
        events.append(event.name)

    app = create_app(
        settings(),
        attachments=AttachmentProcessor(),
        attachment_store=Store(),
        host=HostHooks(on_lifecycle=lifecycle),
        gateway=FakeGateway(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/files/prepare",
            headers={
                "Authorization": "Bearer app-secret",
                "X-Filename": "notes.txt",
                "Content-Type": "text/plain",
            },
            content=b"hello",
        )
    assert response.json()["storage"]["id"] == "app-api-key:notes.txt"
    assert events == ["file.prepare.started", "file.prepare.completed"]


def test_chat_contract_is_authenticated_bounded_and_provider_neutral():
    backend = FakeChatBackend()
    app = create_app(
        settings(max_chat_message_chars=10),
        chat_backend=backend,
        gateway=FakeGateway(),
    )
    with TestClient(app) as client:
        unauthorized = client.post("/v1/chat", json={"message": "hello"})
        response = client.post(
            "/v1/chat",
            headers={"Authorization": "Bearer app-secret", "X-Request-ID": "chat-request"},
            json={"message": "hello", "history": [{"role": "assistant", "content": "Welcome"}]},
        )
        invalid = client.post(
            "/v1/chat",
            headers={"Authorization": "Bearer app-secret"},
            json={"message": "this is too long"},
        )

    assert unauthorized.status_code == 401
    assert unauthorized.json()["error"]["code"] == "unauthorized"
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "chat-request"
    assert response.json() == {
        "message": {"role": "assistant", "content": "Reply to: hello"},
        "tool_calls": [],
        "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
    }
    assert backend.principal.id == "app-api-key"
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_request"


def test_chat_authorization_fails_before_backend_execution():
    backend = FakeChatBackend()

    async def deny(_, authorization):
        return authorization.action != "chat.complete"

    app = create_app(
        settings(),
        host=HostHooks(authorize=deny),
        chat_backend=backend,
        gateway=FakeGateway(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            headers={"Authorization": "Bearer app-secret"},
            json={"message": "hello"},
        )

    assert response.status_code == 403
    assert backend.principal is None


def test_chat_has_an_overall_timeout():
    class SlowChatBackend:
        async def complete(self, request, *, principal, tools, authorize_tool):
            await asyncio.sleep(0.05)
            return ChatResponse(message=ChatMessage(role="assistant", content="too late"))

    app = create_app(
        settings(chat_timeout_seconds=0.001),
        chat_backend=SlowChatBackend(),
        gateway=FakeGateway(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat",
            headers={"Authorization": "Bearer app-secret"},
            json={"message": "hello"},
        )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "chat_timeout"


def test_chat_fails_closed_when_authentication_is_not_configured():
    app = create_app(
        settings(app_api_key=None),
        chat_backend=FakeChatBackend(),
        gateway=FakeGateway(),
    )
    with TestClient(app) as client:
        response = client.post("/v1/chat", json={"message": "hello"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "authentication_unavailable"


def test_direct_tool_execution_obeys_timeout():
    tools = ToolRegistry()

    @tools.tool(name="slow", description="Slow", parameters={"type": "object", "properties": {}})
    async def slow(_, __):
        await asyncio.sleep(0.05)
        return {"ok": True}

    app = create_app(
        settings(tool_timeout_seconds=0.001),
        tools=tools,
        chat_backend=FakeChatBackend(),
        gateway=FakeGateway(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/v1/tools/slow",
            headers={"Authorization": "Bearer app-secret"},
            json={},
        )
    assert response.status_code == 504


def test_custom_chat_backend_can_run_without_openai_or_realtime():
    app = create_app(
        settings(openai_api_key=""),
        chat_backend=FakeChatBackend(),
        enable_realtime=False,
    )
    with TestClient(app) as client:
        chat = client.post(
            "/v1/chat",
            headers={"Authorization": "Bearer app-secret"},
            json={"message": "hello"},
        )
        realtime = client.post(
            "/v1/realtime/token",
            headers={"Authorization": "Bearer app-secret"},
        )
    assert chat.status_code == 200
    assert realtime.status_code == 404
