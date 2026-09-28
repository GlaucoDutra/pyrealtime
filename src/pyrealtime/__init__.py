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
from .demo import DemoChatBackend, create_demo_app
from .doctor import DoctorCheck, DoctorOptions, DoctorReport, format_report, run_doctor
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
from .jev import (
    JevAnswer,
    JevChoiceAnswer,
    JevChoiceQuestion,
    JevClient,
    JevLimits,
    JevNoulAnswer,
    JevNoulQuestion,
    JevQuestion,
    JevRequest,
    JevResponse,
    JevScoreAnswer,
    JevScoreQuestion,
    JevTools,
    JevUsage,
)
from .limits import InMemoryRateLimiter, RateLimit, RateLimitDecision, RateLimiter
from .observability import JsonFormatter, configure_json_logging, redact
from .principal import Principal
from .tools import AppToolRouter, ToolDefinition, ToolRegistry
from .usage import NullUsageSink, UsageEvent, UsageSink
from .starter import generate_starter

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
    "create_demo_app",
    "DemoChatBackend",
    "DoctorCheck",
    "DoctorOptions",
    "DoctorReport",
    "HostHooks",
    "InMemoryRateLimiter",
    "JsonFormatter",
    "JWTAuthenticator",
    "JevAnswer",
    "JevChoiceAnswer",
    "JevChoiceQuestion",
    "JevClient",
    "JevLimits",
    "JevNoulAnswer",
    "JevNoulQuestion",
    "JevQuestion",
    "JevRequest",
    "JevResponse",
    "JevScoreAnswer",
    "JevScoreQuestion",
    "JevTools",
    "JevUsage",
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
    "format_report",
    "generate_starter",
    "redact",
    "run_doctor",
]
