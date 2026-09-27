"""Optional, production-oriented FastAPI application factory."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Mapping
from urllib.parse import unquote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .attachments import AttachmentProcessor, AttachmentStore
from .config import ServerSettings
from .exceptions import AttachmentError, AttachmentTooLargeError, UpstreamError
from .gateway import OpenAIRealtimeGateway
from .host import Authenticator, AuthorizationRequest, HostHooks, LifecycleEvent
from .limits import InMemoryRateLimiter, RateLimit, RateLimiter
from .observability import configure_json_logging
from .principal import Principal
from .tools import ToolRegistry
from .usage import NullUsageSink, UsageEvent, UsageSink

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
logger = logging.getLogger("pyrealtime.api")


def _upstream_error_detail(exc: UpstreamError) -> tuple[str, str | None]:
    code: str | None = None
    upstream_message = ""
    try:
        payload = json.loads(exc.response_body)
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        if isinstance(error, dict):
            upstream_message = str(error.get("message", "")).strip()
            code = str(error.get("code", "")).strip() or None
    except (TypeError, ValueError):
        pass
    if exc.status_code == 401:
        return ("OpenAI rejected the API key. Configure a valid OpenAI project API key.", code)
    if exc.status_code == 403:
        return ("The OpenAI project does not have permission to use this Realtime model.", code)
    if exc.status_code == 429:
        return ("OpenAI rate limits or project quota prevented creation of the Realtime session.", code)
    if exc.status_code == 400 and upstream_message:
        return (f"OpenAI rejected the Realtime configuration: {upstream_message}", code)
    return (str(exc), code)


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _read_limited(request: Request, maximum: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > maximum:
        raise HTTPException(status_code=413, detail="Request body exceeds the configured size limit")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum:
            raise HTTPException(status_code=413, detail="Request body exceeds the configured size limit")
    return bytes(body)


def create_app(
    settings: ServerSettings,
    *,
    tools: ToolRegistry | None = None,
    authenticate: Authenticator | None = None,
    host: HostHooks | None = None,
    gateway: OpenAIRealtimeGateway | None = None,
    attachments: AttachmentProcessor | None = None,
    attachment_store: AttachmentStore | None = None,
    rate_limiter: RateLimiter | None = None,
    usage_sink: UsageSink | None = None,
) -> FastAPI:
    """Create the reusable API while leaving identity, policy, storage, and billing host-owned."""

    registry = tools or ToolRegistry()
    hooks = host or HostHooks()
    limiter = rate_limiter or InMemoryRateLimiter()
    usage = usage_sink or NullUsageSink()
    realtime_gateway = gateway or OpenAIRealtimeGateway(
        api_key=settings.openai_api_key,
        timeout=settings.request_timeout_seconds,
    )
    owns_gateway = gateway is None
    if settings.json_logs:
        configure_json_logging()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if owns_gateway:
            await realtime_gateway.aclose()

    app = FastAPI(title="PyRealtime API", version="0.2.0", lifespan=lifespan)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials="*" not in settings.cors_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Filename", settings.request_id_header],
            expose_headers=[settings.request_id_header, "Retry-After"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        supplied = request.headers.get(settings.request_id_header, "")
        request_id = supplied if _REQUEST_ID.fullmatch(supplied) else uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers[settings.request_id_header] = request_id
            return response
        finally:
            logger.info(
                "request.completed",
                extra={"fields": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                }},
            )

    @app.exception_handler(UpstreamError)
    async def upstream_error_handler(_: Request, exc: UpstreamError) -> JSONResponse:
        detail, code = _upstream_error_detail(exc)
        return JSONResponse(status_code=502, content={
            "detail": detail,
            "upstream_status": exc.status_code or None,
            "upstream_code": code,
        })

    async def resolve_principal(request: Request) -> Principal:
        if authenticate is not None:
            principal = await _await(authenticate(request))
            if not isinstance(principal, Principal):
                raise HTTPException(status_code=401, detail="Authentication did not return a Principal")
        elif settings.app_api_key:
            supplied = _bearer_token(request)
            if not supplied or not secrets.compare_digest(supplied, settings.app_api_key):
                raise HTTPException(status_code=401, detail="Invalid application token")
            principal = Principal(id="app-api-key")
        elif settings.allow_anonymous:
            principal = Principal(id="anonymous")
        else:
            raise HTTPException(status_code=503, detail="Application authentication is not configured")
        request.state.principal_id = principal.id
        return principal

    async def authorize(principal: Principal, request: Request, action: str, resource: str | None = None) -> None:
        if hooks.authorize is None:
            return
        allowed = await _await(hooks.authorize(principal, AuthorizationRequest(
            action=action,
            request_id=request.state.request_id,
            resource=resource,
        )))
        if not allowed:
            raise HTTPException(status_code=403, detail="The authenticated principal is not authorized for this action")

    async def apply_limit(principal: Principal, scope: str, requests: int) -> None:
        decision = await limiter.acquire(
            scope,
            principal.id,
            RateLimit(requests=requests, window_seconds=settings.rate_limit_window_seconds),
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for {scope}",
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )

    async def emit(name: str, request: Request, principal: Principal, **details: Any) -> None:
        if hooks.on_lifecycle is not None:
            try:
                await _await(hooks.on_lifecycle(LifecycleEvent(
                    name=name,
                    request_id=request.state.request_id,
                    principal_id=principal.id,
                    details=details,
                )))
            except Exception:
                logger.exception("lifecycle_hook.failed", extra={"fields": {"request_id": request.state.request_id, "event": name}})

    async def record(kind: str, request: Request, principal: Principal, **metadata: Any) -> None:
        try:
            await usage.record(UsageEvent(
                kind=kind,
                principal_id=principal.id,
                request_id=request.state.request_id,
                metadata=metadata,
            ))
        except Exception:
            logger.exception("usage_sink.failed", extra={"fields": {"request_id": request.state.request_id, "kind": kind}})

    @asynccontextmanager
    async def operation(name: str, request: Request, principal: Principal, **details: Any):
        await emit(f"{name}.started", request, principal, **details)
        try:
            yield
        except Exception as exc:
            await emit(f"{name}.failed", request, principal, error_type=type(exc).__name__, **details)
            raise
        else:
            await emit(f"{name}.completed", request, principal, **details)

    @app.get("/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "pyrealtime", "version": "0.2.0"}

    @app.post("/v1/realtime/token")
    async def realtime_token(request: Request, principal: Principal = Depends(resolve_principal)) -> Mapping[str, Any]:
        await authorize(principal, request, "realtime.session")
        await apply_limit(principal, "realtime.session", settings.session_rate_limit)
        async with operation("realtime.session", request, principal, transport="client_secret"):
            config = settings.session_config(tools=registry.schemas())
            result = await realtime_gateway.create_client_secret(
                config,
                safety_identifier=hashlib.sha256(principal.id.encode()).hexdigest(),
            )
        await record("realtime.session", request, principal, transport="client_secret")
        return result

    @app.post("/v1/realtime/session", response_class=PlainTextResponse)
    async def realtime_session(request: Request, principal: Principal = Depends(resolve_principal)) -> PlainTextResponse:
        await authorize(principal, request, "realtime.session")
        await apply_limit(principal, "realtime.session", settings.session_rate_limit)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"application/sdp", "text/plain"}:
            raise HTTPException(status_code=415, detail="Expected an SDP request body")
        try:
            sdp_offer = (await _read_limited(request, settings.max_sdp_bytes)).decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="SDP body must be UTF-8") from exc
        async with operation("realtime.session", request, principal, transport="webrtc"):
            answer = await realtime_gateway.create_webrtc_call(
                sdp_offer,
                settings.session_config(tools=registry.schemas()),
                safety_identifier=hashlib.sha256(principal.id.encode()).hexdigest(),
            )
        await record("realtime.session", request, principal, transport="webrtc")
        return PlainTextResponse(answer, media_type="application/sdp")

    @app.post("/v1/tools/{tool_name}")
    async def run_tool(tool_name: str, request: Request, principal: Principal = Depends(resolve_principal)) -> Any:
        await authorize(principal, request, "tool.execute", tool_name)
        await apply_limit(principal, "tool.execute", settings.tool_rate_limit)
        body = await _read_limited(request, settings.max_tool_request_bytes)
        try:
            arguments = json.loads(body or b"{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail="Tool arguments must be a JSON object") from exc
        if not isinstance(arguments, dict):
            raise HTTPException(status_code=400, detail="Tool arguments must be a JSON object")
        async with operation("tool", request, principal, tool=tool_name):
            try:
                result = await registry.execute(tool_name, arguments, principal)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        await record("tool.call", request, principal, tool=tool_name)
        return result

    if attachments is not None:
        @app.post("/v1/files/prepare")
        async def prepare_file(request: Request, principal: Principal = Depends(resolve_principal)) -> dict[str, Any]:
            await authorize(principal, request, "file.prepare")
            await apply_limit(principal, "file.prepare", settings.file_rate_limit)
            raw_name = request.headers.get("x-filename", "")
            try:
                filename = unquote(raw_name, errors="strict")
            except UnicodeDecodeError as exc:
                raise HTTPException(status_code=400, detail="Invalid X-Filename encoding") from exc
            body = await _read_limited(request, attachments.policy.max_file_bytes)
            async with operation("file.prepare", request, principal, filename=filename):
                try:
                    prepared = await attachments.prepare(filename, request.headers.get("content-type", "application/octet-stream"), body)
                except AttachmentTooLargeError as exc:
                    raise HTTPException(status_code=413, detail=str(exc)) from exc
                except AttachmentError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                result = prepared.to_dict()
                if attachment_store is not None:
                    result["storage"] = dict(await attachment_store.save(principal.id, prepared))
            await record("file.prepare", request, principal, media_type=prepared.media_type, size_bytes=prepared.size_bytes)
            return result

    return app
