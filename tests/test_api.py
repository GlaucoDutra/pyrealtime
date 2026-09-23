from fastapi.testclient import TestClient

from pyrealtime import AttachmentProcessor, Principal, ServerSettings, ToolRegistry
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
    assert gateway.config.model == "gpt-realtime-2.1"


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
        "detail": "OpenAI rejected the API key. Enter a valid OpenAI project API key and restart the local prototype.",
        "upstream_status": 401,
        "upstream_code": "invalid_api_key",
    }
