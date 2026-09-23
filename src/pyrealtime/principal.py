"""Authenticated application identity."""

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Principal:
    """Identity produced by the host application's authentication layer."""

    id: str
    access_token: str | None = None
    claims: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Principal.id cannot be empty")

