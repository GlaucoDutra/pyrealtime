"""Reference JWT authentication adapters for host applications."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .principal import Principal


def _bearer(request: Any) -> str:
    value = request.headers.get("authorization", "")
    scheme, _, token = value.partition(" ")
    return token.strip() if scheme.lower() == "bearer" else ""


@dataclass(slots=True)
class JWTAuthenticator:
    """Validate bearer JWTs using either a shared secret or a JWKS endpoint."""

    algorithms: Sequence[str]
    audience: str | None = None
    issuer: str | None = None
    shared_secret: str | None = None
    jwks_url: str | None = None
    subject_claim: str = "sub"

    def __post_init__(self) -> None:
        if bool(self.shared_secret) == bool(self.jwks_url):
            raise ValueError("Configure exactly one of shared_secret or jwks_url")
        if not self.algorithms:
            raise ValueError("At least one JWT algorithm is required")

    async def __call__(self, request: Any) -> Principal:
        try:
            import jwt
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("JWT authentication requires pyrealtime-ai[auth]") from exc
        token = _bearer(request)
        if not token:
            return self._unauthorized("Bearer token is required")
        try:
            if self.shared_secret:
                key: Any = self.shared_secret
            else:
                client = jwt.PyJWKClient(str(self.jwks_url))
                signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
                key = signing_key.key
            claims: Mapping[str, Any] = jwt.decode(
                token,
                key,
                algorithms=list(self.algorithms),
                audience=self.audience,
                issuer=self.issuer,
                options={"require": [self.subject_claim]},
            )
        except jwt.PyJWTError:
            return self._unauthorized("Invalid bearer token")
        subject = str(claims.get(self.subject_claim, "")).strip()
        if not subject:
            return self._unauthorized("JWT subject is missing")
        return Principal(id=subject, access_token=token, claims=dict(claims))

    @staticmethod
    def _unauthorized(detail: str) -> Principal:
        try:
            from fastapi import HTTPException
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(detail) from exc
        raise HTTPException(status_code=401, detail=detail)
