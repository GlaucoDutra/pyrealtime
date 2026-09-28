from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from pyrealtime import DoctorOptions, create_demo_app, format_report, generate_starter, run_doctor
from pyrealtime.cli import main as cli_main


def test_starter_generator_creates_complete_safe_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "new-app"
    created = generate_starter(target)

    assert {path.name for path in created} == {
        "app.py", ".env.example", ".gitignore", "requirements.txt", "README.md",
    }
    assert "v0.3.0/pyrealtime_ai-0.3.0-py3-none-any.whl" in (target / "requirements.txt").read_text()
    assert "PYREALTIME_DEMO=true" in (target / ".env.example").read_text()
    assert "HostHooks" in (target / "app.py").read_text()

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("APP_API_KEY", raising=False)
    monkeypatch.setenv("PYREALTIME_DEMO", "true")
    spec = importlib.util.spec_from_file_location("generated_starter_app", target / "app.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    paths = {route.path for route in module.app.routes}
    assert "/ai" in paths


def test_starter_never_overwrites_existing_files(tmp_path: Path):
    target = tmp_path / "existing"
    target.mkdir()
    marker = target / "keep.txt"
    marker.write_text("do not replace")

    with pytest.raises(FileExistsError):
        generate_starter(target)

    assert marker.read_text() == "do not replace"


def test_cli_init_generates_project(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    target = tmp_path / "cli-app"
    assert cli_main(["init", str(target)]) == 0
    assert (target / "app.py").is_file()
    assert "Created PyRealtime starter" in capsys.readouterr().out


def test_cli_demo_refuses_non_loopback_host(capsys: pytest.CaptureFixture[str]):
    assert cli_main(["demo", "--host", "0.0.0.0"]) == 2
    assert "loopback" in capsys.readouterr().out


def test_no_key_demo_is_labeled_authenticated_and_has_tool():
    app = create_demo_app(token="demo-test-token")
    headers = {"Authorization": "Bearer demo-test-token"}
    with TestClient(app) as client:
        unauthorized = client.post("/v1/chat", json={"message": "hello"})
        chat = client.post("/v1/chat", headers=headers, json={"message": "hello"})
        tool = client.post("/v1/tools/get_status", headers=headers, json={})
        realtime = client.post("/v1/realtime/token", headers=headers)

    assert unauthorized.status_code == 401
    assert "DEMO MODE" in chat.json()["message"]["content"]
    assert chat.json()["usage"] is None
    assert tool.json() == {"status": "demo-ready", "principal_id": "app-api-key"}
    assert realtime.status_code == 404


def test_doctor_checks_api_openai_and_cors_without_exposing_secrets(monkeypatch: pytest.MonkeyPatch):
    secret = "sk-never-print-this"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setenv("APP_API_KEY", "also-never-print-this")
    monkeypatch.setenv("APP_CORS_ORIGINS", "http://localhost:3000")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.openai.com":
            assert request.headers["authorization"] == f"Bearer {secret}"
            return httpx.Response(200, json={"id": "gpt-5-mini"})
        if request.method == "OPTIONS":
            return httpx.Response(200, headers={"Access-Control-Allow-Origin": "http://localhost:3000"})
        return httpx.Response(200, json={"status": "ok"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        report = run_doctor(
            DoctorOptions(api_url="http://api.test/ai", origin="http://localhost:3000"),
            http_client=client,
        )

    rendered = format_report(report)
    assert report.ok
    assert "API connectivity: health endpoint reachable" in rendered
    assert "CORS preflight: preflight accepted" in rendered
    assert "OpenAI connectivity: API key and chat model accepted" in rendered
    assert secret not in rendered
    assert "also-never-print-this" not in rendered


def test_doctor_offline_mode_is_useful_without_keys(monkeypatch: pytest.MonkeyPatch):
    for key in ("OPENAI_API_KEY", "APP_API_KEY", "APP_CORS_ORIGINS"):
        monkeypatch.delenv(key, raising=False)
    report = run_doctor(DoctorOptions(network=False, check_openai=False))
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["settings"] == "pass"
    assert statuses["OpenAI key"] == "warn"
    assert statuses["API connectivity"] == "skip"
    assert report.exit_code() == 0
    assert report.exit_code(strict=True) == 1
