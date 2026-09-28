"""Configuration models for Realtime sessions and the application API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class RealtimeSessionConfig:
    """Server-controlled configuration used to mint a browser client secret."""

    model: str = "gpt-realtime-2.1-mini"
    voice: str = "marin"
    instructions: str = ""
    output_modalities: tuple[str, ...] = ("audio",)
    transcription_model: str | None = "gpt-4o-mini-transcribe"
    vad_type: str | None = "server_vad"
    vad_threshold: float = 0.5
    prefix_padding_ms: int = 300
    silence_duration_ms: int = 500
    create_response: bool = True
    interrupt_response: bool = True
    tools: Sequence[Mapping[str, Any]] = field(default_factory=tuple)
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        if not self.voice.strip():
            raise ValueError("voice cannot be empty")
        if not 0 <= self.vad_threshold <= 1:
            raise ValueError("vad_threshold must be between 0 and 1")
        if self.prefix_padding_ms < 0 or self.silence_duration_ms < 0:
            raise ValueError("VAD timing values cannot be negative")

    def to_session(self) -> dict[str, Any]:
        session: dict[str, Any] = {
            "type": "realtime",
            "model": self.model,
            "output_modalities": list(self.output_modalities),
            "audio": {
                "output": {
                    "voice": self.voice,
                },
            },
        }

        if self.instructions:
            session["instructions"] = self.instructions

        audio_input: dict[str, Any] = {}
        if self.transcription_model:
            audio_input["transcription"] = {"model": self.transcription_model}
        if self.vad_type:
            audio_input["turn_detection"] = {
                "type": self.vad_type,
                "threshold": self.vad_threshold,
                "prefix_padding_ms": self.prefix_padding_ms,
                "silence_duration_ms": self.silence_duration_ms,
                "create_response": self.create_response,
                "interrupt_response": self.interrupt_response,
            }
        if audio_input:
            session["audio"]["input"] = audio_input

        if self.tools:
            session["tools"] = [dict(tool) for tool in self.tools]

        session.update(dict(self.extra))
        return session

    def to_client_secret_payload(self) -> dict[str, Any]:
        return {"session": self.to_session()}


@dataclass(frozen=True, slots=True)
class ServerSettings:
    """Runtime settings for the optional application API."""

    openai_api_key: str
    app_base_url: str = "http://localhost:8000"
    app_api_key: str | None = None
    cors_origins: tuple[str, ...] = ()
    allow_anonymous: bool = False
    request_timeout_seconds: float = 20.0
    tool_timeout_seconds: float = 120.0
    realtime_model: str = "gpt-realtime-2.1-mini"
    realtime_voice: str = "marin"
    realtime_instructions: str = "You are a concise and helpful realtime assistant."
    tool_model: str = "gpt-5-mini"
    chat_model: str = "gpt-5-mini"
    chat_instructions: str = "You are a concise and helpful assistant."
    image_model: str = "gpt-image-2.5-flare"
    vector_store_ids: tuple[str, ...] = ()
    max_sdp_bytes: int = 1_000_000
    max_tool_request_bytes: int = 64_000
    max_chat_request_bytes: int = 256_000
    max_chat_message_chars: int = 32_000
    max_chat_history_messages: int = 20
    max_chat_history_chars: int = 120_000
    max_chat_tool_rounds: int = 4
    max_chat_tool_result_chars: int = 32_000
    chat_max_output_tokens: int = 2_048
    chat_timeout_seconds: float = 120.0
    session_rate_limit: int = 10
    chat_rate_limit: int = 30
    tool_rate_limit: int = 60
    file_rate_limit: int = 10
    rate_limit_window_seconds: int = 60
    request_id_header: str = "X-Request-ID"
    json_logs: bool = True
    typesafe_api_key: str = ""
    jev_model: str = "jev-latest"
    jev_timeout_seconds: float = 10.0
    jev_max_state_bytes: int = 128_000
    jev_max_questions: int = 16
    jev_max_instructions_chars: int = 1_000
    jev_max_criteria: int = 64
    jev_max_criterion_chars: int = 1_000

    def __post_init__(self) -> None:
        positive = {
            "max_sdp_bytes": self.max_sdp_bytes,
            "max_tool_request_bytes": self.max_tool_request_bytes,
            "max_chat_request_bytes": self.max_chat_request_bytes,
            "max_chat_message_chars": self.max_chat_message_chars,
            "max_chat_history_messages": self.max_chat_history_messages,
            "max_chat_history_chars": self.max_chat_history_chars,
            "max_chat_tool_rounds": self.max_chat_tool_rounds,
            "max_chat_tool_result_chars": self.max_chat_tool_result_chars,
            "chat_max_output_tokens": self.chat_max_output_tokens,
            "rate_limit_window_seconds": self.rate_limit_window_seconds,
            "jev_max_state_bytes": self.jev_max_state_bytes,
            "jev_max_questions": self.jev_max_questions,
            "jev_max_instructions_chars": self.jev_max_instructions_chars,
            "jev_max_criteria": self.jev_max_criteria,
            "jev_max_criterion_chars": self.jev_max_criterion_chars,
        }
        if any(value <= 0 for value in positive.values()):
            raise ValueError("Request-size and rate-window settings must be positive")
        if self.chat_timeout_seconds <= 0:
            raise ValueError("chat_timeout_seconds must be positive")
        if self.request_timeout_seconds <= 0 or self.tool_timeout_seconds <= 0:
            raise ValueError("Request and tool timeouts must be positive")
        if self.jev_timeout_seconds <= 0:
            raise ValueError("jev_timeout_seconds must be positive")
        if not self.jev_model.strip():
            raise ValueError("jev_model cannot be empty")
        if self.jev_max_questions > 64 or self.jev_max_criteria > 255:
            raise ValueError("JEV limits exceed the public schema maximum")
        if self.max_chat_history_messages > 100:
            raise ValueError("max_chat_history_messages cannot exceed the public schema limit of 100")
        if self.max_chat_message_chars > 64_000:
            raise ValueError("max_chat_message_chars cannot exceed the public schema limit of 64000")
        if min(self.session_rate_limit, self.chat_rate_limit, self.tool_rate_limit, self.file_rate_limit) < 0:
            raise ValueError("Rate limits cannot be negative")

    @classmethod
    def from_env(cls) -> "ServerSettings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            typesafe_api_key=os.getenv("TYPESAFE_API_KEY", "").strip(),
            app_base_url=os.getenv("APP_BASE_URL", "http://localhost:8000").strip(),
            app_api_key=os.getenv("APP_API_KEY", "").strip() or None,
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv("APP_CORS_ORIGINS", "").split(",")
                if origin.strip()
            ),
            allow_anonymous=os.getenv("PYREALTIME_ALLOW_ANONYMOUS", "false").lower() in {"1", "true", "yes"},
            request_timeout_seconds=float(os.getenv("PYREALTIME_REQUEST_TIMEOUT_SECONDS", "20")),
            tool_timeout_seconds=float(os.getenv("PYREALTIME_TOOL_TIMEOUT_SECONDS", "120")),
            realtime_model=os.getenv("PYREALTIME_MODEL", "gpt-realtime-2.1-mini").strip(),
            realtime_voice=os.getenv("PYREALTIME_VOICE", "marin").strip(),
            realtime_instructions=os.getenv(
                "PYREALTIME_INSTRUCTIONS",
                "You are a concise and helpful realtime assistant.",
            ).strip(),
            tool_model=os.getenv("PYREALTIME_TOOL_MODEL", "gpt-5-mini").strip(),
            chat_model=os.getenv("PYREALTIME_CHAT_MODEL", "gpt-5-mini").strip(),
            chat_instructions=os.getenv(
                "PYREALTIME_CHAT_INSTRUCTIONS",
                "You are a concise and helpful assistant.",
            ).strip(),
            image_model=os.getenv("PYREALTIME_IMAGE_MODEL", "gpt-image-2.5-flare").strip(),
            vector_store_ids=tuple(
                value.strip()
                for value in os.getenv("PYREALTIME_VECTOR_STORE_IDS", "").split(",")
                if value.strip()
            ),
            max_sdp_bytes=int(os.getenv("PYREALTIME_MAX_SDP_BYTES", "1000000")),
            max_tool_request_bytes=int(os.getenv("PYREALTIME_MAX_TOOL_REQUEST_BYTES", "64000")),
            max_chat_request_bytes=int(os.getenv("PYREALTIME_MAX_CHAT_REQUEST_BYTES", "256000")),
            max_chat_message_chars=int(os.getenv("PYREALTIME_MAX_CHAT_MESSAGE_CHARS", "32000")),
            max_chat_history_messages=int(os.getenv("PYREALTIME_MAX_CHAT_HISTORY_MESSAGES", "20")),
            max_chat_history_chars=int(os.getenv("PYREALTIME_MAX_CHAT_HISTORY_CHARS", "120000")),
            max_chat_tool_rounds=int(os.getenv("PYREALTIME_MAX_CHAT_TOOL_ROUNDS", "4")),
            max_chat_tool_result_chars=int(os.getenv("PYREALTIME_MAX_CHAT_TOOL_RESULT_CHARS", "32000")),
            chat_max_output_tokens=int(os.getenv("PYREALTIME_CHAT_MAX_OUTPUT_TOKENS", "2048")),
            chat_timeout_seconds=float(os.getenv("PYREALTIME_CHAT_TIMEOUT_SECONDS", "120")),
            session_rate_limit=int(os.getenv("PYREALTIME_SESSION_RATE_LIMIT", "10")),
            chat_rate_limit=int(os.getenv("PYREALTIME_CHAT_RATE_LIMIT", "30")),
            tool_rate_limit=int(os.getenv("PYREALTIME_TOOL_RATE_LIMIT", "60")),
            file_rate_limit=int(os.getenv("PYREALTIME_FILE_RATE_LIMIT", "10")),
            rate_limit_window_seconds=int(os.getenv("PYREALTIME_RATE_LIMIT_WINDOW_SECONDS", "60")),
            request_id_header=os.getenv("PYREALTIME_REQUEST_ID_HEADER", "X-Request-ID").strip(),
            json_logs=os.getenv("PYREALTIME_JSON_LOGS", "true").lower() in {"1", "true", "yes"},
            jev_model=os.getenv("PYREALTIME_JEV_MODEL", "jev-latest").strip(),
            jev_timeout_seconds=float(os.getenv("PYREALTIME_JEV_TIMEOUT_SECONDS", "10")),
            jev_max_state_bytes=int(os.getenv("PYREALTIME_JEV_MAX_STATE_BYTES", "128000")),
            jev_max_questions=int(os.getenv("PYREALTIME_JEV_MAX_QUESTIONS", "16")),
            jev_max_instructions_chars=int(os.getenv("PYREALTIME_JEV_MAX_INSTRUCTIONS_CHARS", "1000")),
            jev_max_criteria=int(os.getenv("PYREALTIME_JEV_MAX_CRITERIA", "64")),
            jev_max_criterion_chars=int(os.getenv("PYREALTIME_JEV_MAX_CRITERION_CHARS", "1000")),
        )

    def jev_limits(self) -> "JevLimits":
        """Build reusable JEV limits from server configuration."""
        from .jev import JevLimits

        return JevLimits(
            max_state_bytes=self.jev_max_state_bytes,
            max_questions=self.jev_max_questions,
            max_instructions_chars=self.jev_max_instructions_chars,
            max_criteria=self.jev_max_criteria,
            max_criterion_chars=self.jev_max_criterion_chars,
        )

    def session_config(self, *, tools: Sequence[Mapping[str, Any]] = ()) -> RealtimeSessionConfig:
        return RealtimeSessionConfig(
            model=self.realtime_model,
            voice=self.realtime_voice,
            instructions=self.realtime_instructions,
            tools=tools,
        )
