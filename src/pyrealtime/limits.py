"""Pluggable request rate limiting primitives."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RateLimit:
    requests: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.requests < 0 or self.window_seconds <= 0:
            raise ValueError("Rate limits require non-negative requests and a positive window")


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int = 0


class RateLimiter(Protocol):
    async def acquire(self, scope: str, subject: str, limit: RateLimit) -> RateLimitDecision: ...


class InMemoryRateLimiter:
    """Process-local fixed-window limiter suitable for one-instance deployments and tests."""

    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def acquire(self, scope: str, subject: str, limit: RateLimit) -> RateLimitDecision:
        if limit.requests == 0:
            return RateLimitDecision(True)
        now = time.monotonic()
        cutoff = now - limit.window_seconds
        key = (scope, subject)
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit.requests:
                retry_after = max(1, int(limit.window_seconds - (now - events[0]) + 0.999))
                return RateLimitDecision(False, retry_after)
            events.append(now)
        return RateLimitDecision(True)
