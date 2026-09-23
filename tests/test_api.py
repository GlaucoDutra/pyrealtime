from fastapi.testclient import TestClient

from pyrealtime import Principal, ServerSettings, ToolRegistry
from pyrealtime.api import create_app


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
