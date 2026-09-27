"""Typed contracts between PyRealtime and its host application."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping

if TYPE_CHECKING:
    from fastapi import Request
else:
    Request = Any

from .principal import Principal


Authenticator = Callable[[Request], Principal | Awaitable[Principal]]


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    action: str
    request_id: str
    resource: str | None = None


Authorizer = Callable[[Principal, AuthorizationRequest], bool | Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class LifecycleEvent:
    name: str
    request_id: str
    principal_id: str
    details: Mapping[str, Any] = field(default_factory=dict)


LifecycleHook = Callable[[LifecycleEvent], None | Awaitable[None]]


@dataclass(frozen=True, slots=True)
class HostHooks:
    """Optional host policy callbacks. Company and tenant policy stays outside the core."""

    authorize: Authorizer | None = None
    on_lifecycle: LifecycleHook | None = None
