"""PyRealtime public API."""

from .app_client import AppClient
from .attachments import AttachmentPolicy, AttachmentProcessor, AttachmentStore, PreparedAttachment
from .auth import JWTAuthenticator
from .config import RealtimeSessionConfig, ServerSettings
from .exceptions import (
    AttachmentError,
    AttachmentTooLargeError,
    AuthenticationError,
    ConfigurationError,
    PyRealtimeError,
    UpstreamError,
)
from .gateway import OpenAIRealtimeGateway
from .host import AuthorizationRequest, HostHooks, LifecycleEvent
from .hosted_tools import OpenAIHostedTools, VectorStoreResolver
from .limits import InMemoryRateLimiter, RateLimit, RateLimitDecision, RateLimiter
from .observability import JsonFormatter, configure_json_logging, redact
from .principal import Principal
from .tools import AppToolRouter, ToolDefinition, ToolRegistry
from .usage import NullUsageSink, UsageEvent, UsageSink

__all__ = [
    "AppClient",
    "AppToolRouter",
    "AttachmentError",
    "AttachmentPolicy",
    "AttachmentProcessor",
    "AttachmentStore",
    "AttachmentTooLargeError",
    "AuthenticationError",
    "AuthorizationRequest",
    "ConfigurationError",
    "HostHooks",
    "InMemoryRateLimiter",
    "JsonFormatter",
    "JWTAuthenticator",
    "LifecycleEvent",
    "NullUsageSink",
    "OpenAIRealtimeGateway",
    "OpenAIHostedTools",
    "Principal",
    "PreparedAttachment",
    "RealtimeSessionConfig",
    "ServerSettings",
    "PyRealtimeError",
    "RateLimit",
    "RateLimitDecision",
    "RateLimiter",
    "ToolDefinition",
    "ToolRegistry",
    "UpstreamError",
    "UsageEvent",
    "UsageSink",
    "VectorStoreResolver",
    "configure_json_logging",
    "redact",
]

__version__ = "0.2.0"
