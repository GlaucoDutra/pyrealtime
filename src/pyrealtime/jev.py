"""Bounded TypeSafe JEV decisions and an optional agent tool."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Mapping
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from .exceptions import UpstreamError
from .principal import Principal
from .tools import ToolRegistry

QUESTION_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JevChoiceQuestion(_StrictModel):
    """Select one named criterion."""

    type: Literal["choice"] = "choice"
    instructions: str = Field(min_length=1, max_length=4_000)
    criteria: dict[str, str] = Field(min_length=2, max_length=255)

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, value: dict[str, str]) -> dict[str, str]:
        for name, description in value.items():
            if not QUESTION_NAME_RE.fullmatch(name):
                raise ValueError(f"invalid criterion name: {name!r}")
            if not description.strip() or len(description) > 4_000:
                raise ValueError("criterion descriptions must contain 1 to 4000 characters")
        return value


class JevScoreQuestion(_StrictModel):
    """Score state against an ordered list of criteria."""

    type: Literal["score"] = "score"
    instructions: str = Field(min_length=1, max_length=4_000)
    criteria: list[str] = Field(min_length=2, max_length=255)

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 4_000 for item in value):
            raise ValueError("score criteria must contain 1 to 4000 characters")
        return value


class JevNoulQuestion(_StrictModel):
    """Return JEV's continuous negative/uncertain/positive decision value."""

    type: Literal["noul"] = "noul"
    instructions: str = Field(min_length=1, max_length=4_000)


JevQuestion = Annotated[
    JevChoiceQuestion | JevScoreQuestion | JevNoulQuestion,
    Field(discriminator="type"),
]
_QUESTION_ADAPTER = TypeAdapter(JevQuestion)


class JevRequest(_StrictModel):
    """Provider request accepted by :meth:`JevClient.system_one`."""

    state: str | dict[str, Any] | list[Any]
    questions: dict[str, JevQuestion] = Field(min_length=1, max_length=64)
    model: str = Field(default="jev-latest", min_length=1, max_length=100)

    @field_validator("state")
    @classmethod
    def validate_state(cls, value: str | dict[str, Any] | list[Any]) -> str | dict[str, Any] | list[Any]:
        if isinstance(value, str) and not value.strip():
            raise ValueError("state cannot be empty")
        return value

    @field_validator("questions")
    @classmethod
    def validate_question_names(cls, value: dict[str, JevQuestion]) -> dict[str, JevQuestion]:
        for name in value:
            if not QUESTION_NAME_RE.fullmatch(name):
                raise ValueError(f"invalid question name: {name!r}")
        return value


class JevChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    type: Literal["choice"]
    choice: str
    confidence: float = Field(ge=0, le=1)
    probabilities: dict[str, float]


class JevScoreAnswer(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    type: Literal["score"]
    score: float
    confidence: float = Field(ge=0, le=1)
    legend: dict[str, str]
    probabilities: dict[str, float]


class JevNoulAnswer(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    type: Literal["noul"]
    noul: float


JevAnswer = Annotated[
    JevChoiceAnswer | JevScoreAnswer | JevNoulAnswer,
    Field(discriminator="type"),
]


class JevUsage(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class JevResponse(BaseModel):
    """Validated, typed System One response."""

    model_config = ConfigDict(extra="allow", frozen=True)
    model: str
    answers: dict[str, JevAnswer]
    usage: JevUsage | None = None


@dataclass(frozen=True, slots=True)
class JevLimits:
    """Process-local validation limits applied before provider traffic."""

    max_state_bytes: int = 128_000
    max_questions: int = 16
    max_instructions_chars: int = 1_000
    max_criteria: int = 64
    max_criterion_chars: int = 1_000

    def __post_init__(self) -> None:
        if min(
            self.max_state_bytes,
            self.max_questions,
            self.max_instructions_chars,
            self.max_criteria,
            self.max_criterion_chars,
        ) <= 0:
            raise ValueError("JEV limits must be positive")
        if self.max_questions > 64 or self.max_criteria > 255:
            raise ValueError("JEV limits exceed the public schema maximum")


class JevClient:
    """Async open call for TypeSafe's provider API, independent of an agent."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "jev-latest",
        base_url: str = "https://api.typesafe.ai",
        timeout: float = 10.0,
        limits: JevLimits | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key cannot be empty")
        if not model.strip():
            raise ValueError("model cannot be empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base_url cannot contain credentials, query, or fragment")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.limits = limits or JevLimits()
        self.http_client = http_client

    async def system_one(
        self,
        *,
        state: str | Mapping[str, Any] | list[Any],
        questions: Mapping[str, JevQuestion | Mapping[str, Any]],
        model: str | None = None,
    ) -> JevResponse:
        """Run arbitrary bounded typed questions against supplied state."""

        if not isinstance(questions, Mapping):
            raise ValueError("questions must be an object")
        request = JevRequest(
            state=dict(state) if isinstance(state, Mapping) else state,
            questions={name: _QUESTION_ADAPTER.validate_python(question) for name, question in questions.items()},
            model=(model or self.model).strip(),
        )
        self._enforce_limits(request)
        body = request.model_dump(mode="json")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            if self.http_client is not None:
                response = await self.http_client.post(
                    f"{self.base_url}/v1/systemone", headers=headers, json=body, timeout=self.timeout
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(f"{self.base_url}/v1/systemone", headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise UpstreamError("TypeSafe JEV request timed out", status_code=504) from exc
        except httpx.RequestError as exc:
            raise UpstreamError("Could not reach TypeSafe JEV") from exc
        if not response.is_success:
            # Provider bodies can contain request details. Do not retain or expose them.
            raise UpstreamError("TypeSafe rejected the JEV request", status_code=response.status_code)
        try:
            return JevResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise UpstreamError("TypeSafe returned an invalid JEV response") from exc

    def _enforce_limits(self, request: JevRequest) -> None:
        try:
            state_size = len(json.dumps(request.state, ensure_ascii=False).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ValueError("state must contain only JSON-compatible values") from exc
        if state_size > self.limits.max_state_bytes:
            raise ValueError(f"state cannot exceed {self.limits.max_state_bytes} encoded bytes")
        if len(request.questions) > self.limits.max_questions:
            raise ValueError(f"questions cannot exceed {self.limits.max_questions} items")
        for question in request.questions.values():
            if len(question.instructions) > self.limits.max_instructions_chars:
                raise ValueError(
                    f"question instructions cannot exceed {self.limits.max_instructions_chars} characters"
                )
            criteria = getattr(question, "criteria", None)
            if criteria is None:
                continue
            if len(criteria) > self.limits.max_criteria:
                raise ValueError(f"question criteria cannot exceed {self.limits.max_criteria} items")
            values = criteria.values() if isinstance(criteria, dict) else criteria
            if any(len(value) > self.limits.max_criterion_chars for value in values):
                raise ValueError(
                    f"criterion descriptions cannot exceed {self.limits.max_criterion_chars} characters"
                )


class JevTools:
    """Register JEV as an opt-in function tool for chat and Realtime agents."""

    def __init__(self, client: JevClient) -> None:
        self.client = client

    def register(self, registry: ToolRegistry, *, name: str = "jev_decide") -> None:
        limits = self.client.limits
        question_variants = [
            {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "choice"},
                    "instructions": {"type": "string", "minLength": 1, "maxLength": limits.max_instructions_chars},
                    "criteria": {
                        "type": "object",
                        "minProperties": 2,
                        "maxProperties": limits.max_criteria,
                        "additionalProperties": {"type": "string", "minLength": 1, "maxLength": limits.max_criterion_chars},
                    },
                },
                "required": ["type", "instructions", "criteria"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "score"},
                    "instructions": {"type": "string", "minLength": 1, "maxLength": limits.max_instructions_chars},
                    "criteria": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": limits.max_criteria,
                        "items": {"type": "string", "minLength": 1, "maxLength": limits.max_criterion_chars},
                    },
                },
                "required": ["type", "instructions", "criteria"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "noul"},
                    "instructions": {"type": "string", "minLength": 1, "maxLength": limits.max_instructions_chars},
                },
                "required": ["type", "instructions"],
                "additionalProperties": False,
            },
        ]

        @registry.tool(
            name=name,
            description=(
                "Ask TypeSafe JEV for fast structured decisions about supplied state. Use atomic Choice, "
                "Score, or Noul questions for classification, ranking, routing, or confidence-sensitive "
                "decisions. Do not use this tool for factual lookup or prose generation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "state": {
                        "description": "The text or JSON-compatible application state to evaluate.",
                        "oneOf": [
                            {"type": "string", "minLength": 1},
                            {"type": "object"},
                            {"type": "array"},
                        ],
                    },
                    "questions": {
                        "type": "object",
                        "minProperties": 1,
                        "maxProperties": limits.max_questions,
                        "propertyNames": {"pattern": "^[A-Za-z0-9_.-]{1,64}$"},
                        "additionalProperties": {"oneOf": question_variants},
                    },
                },
                "required": ["state", "questions"],
                "additionalProperties": False,
            },
        )
        async def jev_decide(arguments: Mapping[str, Any], principal: Principal) -> dict[str, Any]:
            del principal
            response = await self.client.system_one(
                state=arguments.get("state", ""),
                questions=arguments.get("questions", {}),
            )
            return response.model_dump(mode="json")
