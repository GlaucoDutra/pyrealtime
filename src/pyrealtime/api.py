"""Optional FastAPI application factory."""

from __future__ import annotations

import hashlib
import inspect
import secrets
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, Mapping
from urllib.parse import unquote

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .attachments import AttachmentProcessor
from .config import ServerSettings
from .exceptions import AttachmentError, AttachmentTooLargeError, UpstreamError
from .gateway import OpenAIRealtimeGateway
from .principal import Principal
from .tools import ToolRegistry

Authenticator = Callable[[Request], Principal | Awaitable[Principal]]


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return ""
    return token.strip()


def create_app(
    settings: ServerSettings,
    *,
    tools: ToolRegistry | None = None,
    authenticate: Authenticator | None = None,
    gateway: OpenAIRealtimeGateway | None = None,
    attachments: AttachmentProcessor | None = None,
) -> FastAPI:
    """Create an app API without coupling the library to an authentication provider."""

    registry = tools or ToolRegistry()
    realtime_gateway = gateway or OpenAIRealtimeGateway(
        api_key=settings.openai_api_key,
        timeout=settings.request_timeout_seconds,
    )
    owns_gateway = gateway is None

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if owns_gateway:
            await realtime_gateway.aclose()

    app = FastAPI(title="PyRealtime API", version="0.1.0", lifespan=lifespan)

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials="*" not in settings.cors_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Filename"],
        )

    @app.exception_handler(UpstreamError)
    async def upstream_error_handler(_: Request, exc: UpstreamError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={
                "detail": str(exc),
                "upstream_status": exc.status_code or None,
            },
        )

    async def resolve_principal(request: Request) -> Principal:
        if authenticate is not None:
            principal = authenticate(request)
            if inspect.isawaitable(principal):
                principal = await principal
            if not isinstance(principal, Principal):
                raise HTTPException(status_code=401, detail="Authentication did not return a Principal")
            return principal

        if settings.app_api_key:
            supplied = _bearer_token(request)
            if not supplied or not secrets.compare_digest(supplied, settings.app_api_key):
                raise HTTPException(status_code=401, detail="Invalid application token")
            return Principal(id="app-api-key")

        if settings.allow_anonymous:
            return Principal(id="anonymous")

        raise HTTPException(status_code=503, detail="Application authentication is not configured")

    @app.get("/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "pyrealtime"}

    @app.post("/v1/realtime/token")
    async def realtime_token(principal: Principal = Depends(resolve_principal)) -> Mapping[str, Any]:
        safety_identifier = hashlib.sha256(principal.id.encode("utf-8")).hexdigest()
        config = settings.session_config(tools=registry.schemas())
        return await realtime_gateway.create_client_secret(
            config,
            safety_identifier=safety_identifier,
        )

    @app.post("/v1/realtime/session", response_class=PlainTextResponse)
    async def realtime_session(
        request: Request,
        principal: Principal = Depends(resolve_principal),
    ) -> PlainTextResponse:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"application/sdp", "text/plain"}:
            raise HTTPException(status_code=415, detail="Expected an SDP request body")
        sdp_offer = (await request.body()).decode("utf-8", errors="strict")
        safety_identifier = hashlib.sha256(principal.id.encode("utf-8")).hexdigest()
        config = settings.session_config(tools=registry.schemas())
        answer = await realtime_gateway.create_webrtc_call(
            sdp_offer,
            config,
            safety_identifier=safety_identifier,
        )
        return PlainTextResponse(answer, media_type="application/sdp")

    @app.post("/v1/tools/{tool_name}")
    async def run_tool(
        tool_name: str,
        arguments: dict[str, Any],
        principal: Principal = Depends(resolve_principal),
    ) -> Any:
        try:
            return await registry.execute(tool_name, arguments, principal)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if attachments is not None:

        @app.post("/v1/files/prepare")
        async def prepare_file(
            request: Request,
            principal: Principal = Depends(resolve_principal),
        ) -> dict[str, Any]:
            del principal  # Authentication is required; preparation itself is stateless.
            raw_name = request.headers.get("x-filename", "")
            try:
                filename = unquote(raw_name, errors="strict")
            except UnicodeDecodeError as exc:
                raise HTTPException(status_code=400, detail="Invalid X-Filename encoding") from exc
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit() and int(content_length) > attachments.policy.max_file_bytes:
                raise HTTPException(status_code=413, detail="File exceeds the configured size limit")
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > attachments.policy.max_file_bytes:
                    raise HTTPException(status_code=413, detail="File exceeds the configured size limit")
            try:
                prepared = await attachments.prepare(
                    filename,
                    request.headers.get("content-type", "application/octet-stream"),
                    bytes(body),
                )
            except AttachmentTooLargeError as exc:
                raise HTTPException(status_code=413, detail=str(exc)) from exc
            except AttachmentError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return prepared.to_dict()

    return app
