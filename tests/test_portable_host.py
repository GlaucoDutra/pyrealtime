import time

import jwt
from fastapi.testclient import TestClient

from examples.jwt_host_server import build_app
from pyrealtime import ServerSettings


class FakeGateway:
    async def create_client_secret(self, config, *, safety_identifier=None):
        return {"value": "unused"}


def token(secret: str, scope: str) -> str:
    return jwt.encode(
        {
            "sub": "user-42",
            "scope": scope,
            "aud": "pyrealtime-example",
            "iss": "pyrealtime-example-host",
            "exp": int(time.time()) + 60,
        },
        secret,
        algorithm="HS256",
    )


def test_second_host_uses_own_jwt_and_tool_policy():
    secret = "portable-example-secret-that-is-long-enough"
    app = build_app(
        settings=ServerSettings(openai_api_key="unused", json_logs=False),
        jwt_secret=secret,
        gateway=FakeGateway(),
    )
    with TestClient(app) as client:
        denied = client.post(
            "/v1/tools/task_status",
            headers={"Authorization": f"Bearer {token(secret, '')}"},
            json={},
        )
        allowed = client.post(
            "/v1/tools/task_status",
            headers={"Authorization": f"Bearer {token(secret, 'tasks:read')}"},
            json={},
        )
    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json() == {"owner_id": "user-42", "status": "ready"}
