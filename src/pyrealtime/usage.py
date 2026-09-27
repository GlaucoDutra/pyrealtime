"""Optional usage-event boundary; pricing and billing remain host-owned."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class UsageEvent:
    kind: str
    principal_id: str
    request_id: str
    units: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)


class UsageSink(Protocol):
    async def record(self, event: UsageEvent) -> None: ...


class NullUsageSink:
    async def record(self, event: UsageEvent) -> None:
        del event
