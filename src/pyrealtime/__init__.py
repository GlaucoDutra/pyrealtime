"""PyRealtime public API."""

from .app_client import AppClient
from .attachments import AttachmentPolicy, AttachmentProcessor, PreparedAttachment
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
from .principal import Principal
from .tools import AppToolRouter, ToolDefinition, ToolRegistry

__all__ = [
    "AppClient",
    "AppToolRouter",
    "AttachmentError",
    "AttachmentPolicy",
    "AttachmentProcessor",
    "AttachmentTooLargeError",
    "AuthenticationError",
    "ConfigurationError",
    "OpenAIRealtimeGateway",
    "Principal",
    "PreparedAttachment",
    "RealtimeSessionConfig",
    "ServerSettings",
    "PyRealtimeError",
    "ToolDefinition",
    "ToolRegistry",
    "UpstreamError",
]

__version__ = "0.1.0"
