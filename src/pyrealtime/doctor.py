"""Safe setup diagnostics for a PyRealtime host."""

from __future__ import annotations

import importlib.util
import os
import platform
import sys
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

import httpx

from .config import ServerSettings

Status = Literal["pass", "warn", "fail", "skip"]


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    name: str
    status: Status
    message: str


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[DoctorCheck, ...]

    @property
    def ok(self) -> bool:
        return not any(check.status == "fail" for check in self.checks)

    def exit_code(self, *, strict: bool = False) -> int:
        blocked = {"fail", "warn"} if strict else {"fail"}
        return int(any(check.status in blocked for check in self.checks))


@dataclass(frozen=True, slots=True)
class DoctorOptions:
    api_url: str | None = None
    origin: str | None = None
    check_openai: bool = True
    network: bool = True
    timeout_seconds: float = 5.0


def _dependency(name: str, import_name: str, *, required: bool = True) -> DoctorCheck:
    available = importlib.util.find_spec(import_name) is not None
    if available:
        return DoctorCheck(name, "pass", "installed")
    return DoctorCheck(name, "fail" if required else "warn", "not installed")


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    **kwargs: object,
) -> httpx.Response | None:
    try:
        return client.request(method, url, **kwargs)
    except httpx.HTTPError:
        return None


def run_doctor(
    options: DoctorOptions | None = None,
    *,
    http_client: httpx.Client | None = None,
) -> DoctorReport:
    """Inspect setup without returning or logging credentials, prompts, or response bodies."""

    selected = options or DoctorOptions(
        api_url=os.getenv("PYREALTIME_API_URL", "").strip() or None,
        origin=os.getenv("PYREALTIME_DOCTOR_ORIGIN", "").strip() or None,
    )
    checks: list[DoctorCheck] = []
    supported = (3, 10) <= sys.version_info[:2] <= (3, 13)
    checks.append(DoctorCheck(
        "python",
        "pass" if supported else "fail",
        f"{platform.python_version()} ({'supported' if supported else 'requires 3.10-3.13'})",
    ))
    checks.extend((
        _dependency("httpx", "httpx"),
        _dependency("pydantic", "pydantic"),
        _dependency("FastAPI", "fastapi"),
        _dependency("Uvicorn", "uvicorn"),
        _dependency("JWT support", "jwt", required=False),
    ))

    try:
        settings = ServerSettings.from_env()
    except (TypeError, ValueError):
        checks.append(DoctorCheck("settings", "fail", "one or more PyRealtime settings are invalid"))
        return DoctorReport(tuple(checks))
    checks.append(DoctorCheck("settings", "pass", "configuration values are valid"))

    openai_key = bool(settings.openai_api_key)
    checks.append(DoctorCheck(
        "OpenAI key",
        "pass" if openai_key else "warn",
        "configured" if openai_key else "not configured; use explicit demo mode or add a server-side key",
    ))
    auth_configured = bool(settings.app_api_key or settings.allow_anonymous)
    checks.append(DoctorCheck(
        "application auth",
        "pass" if auth_configured else "warn",
        "environment mode configured" if auth_configured else "no environment auth; a host callback may still provide authentication",
    ))

    if selected.origin:
        if settings.cors_origins:
            allowed = selected.origin in settings.cors_origins or "*" in settings.cors_origins
            checks.append(DoctorCheck(
                "CORS configuration",
                "pass" if allowed else "fail",
                "origin is allowed" if allowed else "requested origin is not in APP_CORS_ORIGINS",
            ))
        else:
            checks.append(DoctorCheck(
                "CORS configuration",
                "warn",
                "local APP_CORS_ORIGINS is empty; a running API preflight can still be checked",
            ))
    else:
        checks.append(DoctorCheck("CORS configuration", "warn", "no origin supplied; pass --origin to verify browser access"))

    if not selected.network:
        checks.append(DoctorCheck("API connectivity", "skip", "network checks disabled"))
        checks.append(DoctorCheck("OpenAI connectivity", "skip", "network checks disabled"))
        return DoctorReport(tuple(checks))

    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=selected.timeout_seconds, follow_redirects=False)
    try:
        if selected.api_url:
            base = selected.api_url.rstrip("/")
            health = _request(client, "GET", f"{base}/v1/health")
            healthy = health is not None and health.status_code == 200
            checks.append(DoctorCheck(
                "API connectivity",
                "pass" if healthy else "fail",
                "health endpoint reachable" if healthy else "health endpoint could not be reached successfully",
            ))
            if selected.origin:
                preflight = _request(
                    client,
                    "OPTIONS",
                    f"{base}/v1/chat",
                    headers={
                        "Origin": selected.origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "authorization,content-type",
                    },
                )
                cors_ok = (
                    preflight is not None
                    and preflight.status_code in {200, 204}
                    and preflight.headers.get("access-control-allow-origin") in {selected.origin, "*"}
                )
                checks.append(DoctorCheck(
                    "CORS preflight",
                    "pass" if cors_ok else "fail",
                    "preflight accepted" if cors_ok else "preflight was not accepted by the running API",
                ))
        else:
            checks.append(DoctorCheck("API connectivity", "skip", "pass --api-url to check a running API"))

        if selected.check_openai and openai_key:
            model_url = f"https://api.openai.com/v1/models/{quote(settings.chat_model, safe='')}"
            response = _request(
                client,
                "GET",
                model_url,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            )
            connected = response is not None and response.status_code == 200
            checks.append(DoctorCheck(
                "OpenAI connectivity",
                "pass" if connected else "fail",
                "API key and chat model accepted" if connected else "API key or chat model was not accepted",
            ))
        else:
            reason = "disabled" if not selected.check_openai else "no key configured"
            checks.append(DoctorCheck("OpenAI connectivity", "skip", reason))
    finally:
        if owns_client:
            client.close()
    return DoctorReport(tuple(checks))


def format_report(report: DoctorReport) -> str:
    symbols = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "skip": "SKIP"}
    return "\n".join(f"[{symbols[item.status]}] {item.name}: {item.message}" for item in report.checks)
