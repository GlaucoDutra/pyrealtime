"""Safe request correlation and JSON logging helpers."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Mapping

_SENSITIVE = re.compile(r"(authorization|api[-_]?key|access[-_]?token|secret|password|cookie)", re.I)


def redact(value: Any) -> Any:
    """Recursively redact values whose keys commonly contain credentials."""
    if isinstance(value, Mapping):
        return {str(key): "[REDACTED]" if _SENSITIVE.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, Mapping):
            payload.update(redact(fields))
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_json_logging(level: int = logging.INFO) -> None:
    """Configure the pyrealtime logger once without changing the host root logger."""
    logger = logging.getLogger("pyrealtime")
    if not any(getattr(handler, "_pyrealtime_json", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._pyrealtime_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
