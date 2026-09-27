"""Optional, production-oriented FastAPI application factory."""

from __future__ import annotations

import hashlib
import asyncio
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
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import ValidationError

from .attachments import AttachmentProcessor, AttachmentStore
from ._version import __version__
from .chat import (
    APIErrorResponse,
    ChatBackend,
    ChatExecutionError,
    ChatRequest,
    ChatResponse,
    OpenAIChatLimits,
    OpenAIResponsesChatBackend,
)
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
    chat_backend: ChatBackend | None = None,
    enable_chat: bool = True,
    enable_realtime: bool = True,
) -> FastAPI:
    """Create the reusable API while leaving identity, policy, storage, and billing host-owned."""

    registry = tools or ToolRegistry()
    hooks = host or HostHooks()
    limiter = rate_limiter or InMemoryRateLimiter()
    usage = usage_sink or NullUsageSink()
    chats: ChatBackend | None = None
    if enable_chat:
        chats = chat_backend or OpenAIResponsesChatBackend(
            api_key=settings.openai_api_key,
            model=settings.chat_model,
            instructions=settings.chat_instructions,
            timeout=settings.chat_timeout_seconds,
            limits=OpenAIChatLimits(
                max_tool_rounds=settings.max_chat_tool_rounds,
                tool_timeout_seconds=settings.tool_timeout_seconds,
                max_tool_result_chars=settings.max_chat_tool_result_chars,
                max_output_tokens=settings.chat_max_output_tokens,
            ),
        )
    realtime_gateway: OpenAIRealtimeGateway | None = None
    if enable_realtime:
        realtime_gateway = gateway or OpenAIRealtimeGateway(
            api_key=settings.openai_api_key,
            timeout=settings.request_timeout_seconds,
        )
    owns_gateway = enable_realtime and gateway is None
    if settings.json_logs:
        configure_json_logging()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if owns_gateway and realtime_gateway is not None:
            await realtime_gateway.aclose()

    app = FastAPI(title="PyRealtime API", version=__version__, lifespan=lifespan)

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
    async def upstream_error_handler(request: Request, exc: UpstreamError) -> JSONResponse:
        if request.url.path.endswith("/v1/chat"):
            status = 504 if exc.status_code == 504 else 502
            return _chat_error(request, "provider_error", "The chat provider rejected the request", status)
        detail, code = _upstream_error_detail(exc)
        return JSONResponse(status_code=502, content={
            "detail": detail,
            "upstream_status": exc.status_code or None,
            "upstream_code": code,
        })

    def _chat_error(
        request: Request,
        code: str,
        message: str,
        status_code: int,
        headers: Mapping[str, str] | None = None,
    ) -> JSONResponse:
        payload = APIErrorResponse(error={
            "code": code,
            "message": message,
            "request_id": getattr(request.state, "request_id", ""),
        })
        return JSONResponse(status_code=status_code, content=payload.model_dump(), headers=dict(headers or {}))

    @app.exception_handler(ChatExecutionError)
    async def chat_execution_error_handler(request: Request, exc: ChatExecutionError) -> JSONResponse:
        return _chat_error(request, exc.code, str(exc), exc.status_code)

    @app.exception_handler(HTTPException)
    async def protected_http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        if not request.url.path.endswith("/v1/chat"):
            return await http_exception_handler(request, exc)
        code = {
            400: "invalid_request",
            401: "unauthorized",
            403: "forbidden",
            413: "request_too_large",
            415: "unsupported_media_type",
            429: "rate_limited",
            503: "authentication_unavailable",
            504: "timeout",
        }.get(exc.status_code, "request_failed")
        return _chat_error(request, code, str(exc.detail), exc.status_code, exc.headers)

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
        return {"status": "ok", "service": "pyrealtime", "version": __version__}

    async def chat(request: Request, principal: Principal = Depends(resolve_principal)) -> ChatResponse:
        assert chats is not None
        await authorize(principal, request, "chat.complete")
        await apply_limit(principal, "chat.complete", settings.chat_rate_limit)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise HTTPException(status_code=415, detail="Expected an application/json request body")
        body = await _read_limited(request, settings.max_chat_request_bytes)
        try:
            chat_request = ChatRequest.model_validate_json(body)
        except ValidationError as exc:
            first = exc.errors(include_url=False)[0] if exc.errors() else {}
            location = ".".join(str(value) for value in first.get("loc", ()))
            message = str(first.get("msg", "Invalid chat request"))
            raise HTTPException(
                status_code=400,
                detail=f"{location}: {message}" if location else message,
            ) from exc
        if len(chat_request.message) > settings.max_chat_message_chars:
            raise HTTPException(status_code=400, detail="message exceeds the configured character limit")
        if len(chat_request.history) > settings.max_chat_history_messages:
            raise HTTPException(status_code=400, detail="history exceeds the configured message limit")
        history_chars = sum(len(item.content) for item in chat_request.history)
        if history_chars > settings.max_chat_history_chars:
            raise HTTPException(status_code=400, detail="history exceeds the configured character limit")

        async def authorize_chat_tool(tool_name: str) -> None:
            await authorize(principal, request, "tool.execute", tool_name)

        async with operation("chat", request, principal, history_messages=len(chat_request.history)):
            try:
                result = await asyncio.wait_for(
                    chats.complete(
                        chat_request,
                        principal=principal,
                        tools=registry,
                        authorize_tool=authorize_chat_tool,
                    ),
                    timeout=settings.chat_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise ChatExecutionError(
                    "chat_timeout",
                    "The chat request exceeded the configured timeout",
                    status_code=504,
                ) from exc
        usage_metadata = result.usage.model_dump() if result.usage is not None else {}
        await record("chat.response", request, principal, **usage_metadata)
        return result

    if enable_chat:
        app.add_api_route(
            "/v1/chat",
            chat,
            methods=["POST"],
            response_model=ChatResponse,
            responses={400: {"model": APIErrorResponse}, 401: {"model": APIErrorResponse},
                       403: {"model": APIErrorResponse}, 413: {"model": APIErrorResponse},
                       429: {"model": APIErrorResponse}, 502: {"model": APIErrorResponse},
                       504: {"model": APIErrorResponse}},
        )

    async def realtime_token(request: Request, principal: Principal = Depends(resolve_principal)) -> Mapping[str, Any]:
        assert realtime_gateway is not None
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

    async def realtime_session(request: Request, principal: Principal = Depends(resolve_principal)) -> PlainTextResponse:
        assert realtime_gateway is not None
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

    if enable_realtime:
        app.add_api_route("/v1/realtime/token", realtime_token, methods=["POST"])
        app.add_api_route(
            "/v1/realtime/session",
            realtime_session,
            methods=["POST"],
            response_class=PlainTextResponse,
        )

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
                result = await asyncio.wait_for(
                    registry.execute(tool_name, arguments, principal),
                    timeout=settings.tool_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                raise HTTPException(status_code=504, detail="Tool execution timed out") from exc
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


def mount_py_realtime(
    host_app: Any,
    settings: ServerSettings,
    *,
    path: str = "/pyrealtime",
    **options: Any,
) -> FastAPI:
    """Mount PyRealtime into an existing ASGI/FastAPI app and return the mounted sub-application.

    The default gateways do not hold long-lived network clients, so mounted applications do not
    depend on child lifespan propagation. Injected gateways and backends remain host-owned.
    """

    if not path.startswith("/") or path == "/":
        raise ValueError("path must be a non-root absolute mount path")
    child = create_app(settings, **options)
    host_app.mount(path.rstrip("/"), child, name="pyrealtime")
    return child
