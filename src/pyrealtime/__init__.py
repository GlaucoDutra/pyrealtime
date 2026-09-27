"""PyRealtime public API."""

from ._version import __version__
from .app_client import AppClient
from .attachments import AttachmentPolicy, AttachmentProcessor, AttachmentStore, PreparedAttachment
from .auth import JWTAuthenticator
from .chat import (
    APIErrorDetail,
    APIErrorResponse,
    ChatBackend,
    ChatExecutionError,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ChatToolCall,
    ChatUsage,
    OpenAIChatLimits,
    OpenAIResponsesChatBackend,
)
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
    "__version__",
    "AppClient",
    "AppToolRouter",
    "AttachmentError",
    "AttachmentPolicy",
    "AttachmentProcessor",
    "AttachmentStore",
    "AttachmentTooLargeError",
    "AuthenticationError",
    "AuthorizationRequest",
    "APIErrorDetail",
    "APIErrorResponse",
    "ChatBackend",
    "ChatExecutionError",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ChatToolCall",
    "ChatUsage",
    "ConfigurationError",
    "HostHooks",
    "InMemoryRateLimiter",
    "JsonFormatter",
    "JWTAuthenticator",
    "LifecycleEvent",
    "NullUsageSink",
    "OpenAIRealtimeGateway",
    "OpenAIChatLimits",
    "OpenAIResponsesChatBackend",
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
