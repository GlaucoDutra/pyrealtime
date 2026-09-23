"""Library exceptions."""


class PyRealtimeError(Exception):
    """Base error raised by PyRealtime."""


class ConfigurationError(PyRealtimeError):
    """Raised when required configuration is invalid or missing."""


class AuthenticationError(PyRealtimeError):
    """Raised when application authentication fails."""


class AttachmentError(PyRealtimeError):
    """Raised when an attachment cannot be safely prepared."""


class AttachmentTooLargeError(AttachmentError):
    """Raised when an attachment exceeds a configured transport limit."""


class UpstreamError(PyRealtimeError):
    """Raised when OpenAI or the configured application API rejects a request."""

    def __init__(self, message: str, *, status_code: int = 0, response_body: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
