"""Configuration models for Realtime sessions and the application API."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class RealtimeSessionConfig:
    """Server-controlled configuration used to mint a browser client secret."""

    model: str = "gpt-realtime-2.1"
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
    realtime_model: str = "gpt-realtime-2.1"
    realtime_voice: str = "marin"
    realtime_instructions: str = "You are a concise and helpful realtime assistant."

    @classmethod
    def from_env(cls) -> "ServerSettings":
        return cls(
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            app_base_url=os.getenv("APP_BASE_URL", "http://localhost:8000").strip(),
            app_api_key=os.getenv("APP_API_KEY", "").strip() or None,
            cors_origins=tuple(
                origin.strip()
                for origin in os.getenv("APP_CORS_ORIGINS", "").split(",")
                if origin.strip()
            ),
            allow_anonymous=os.getenv("PYREALTIME_ALLOW_ANONYMOUS", "false").lower() in {"1", "true", "yes"},
            request_timeout_seconds=float(os.getenv("PYREALTIME_REQUEST_TIMEOUT_SECONDS", "20")),
            realtime_model=os.getenv("PYREALTIME_MODEL", "gpt-realtime-2.1").strip(),
            realtime_voice=os.getenv("PYREALTIME_VOICE", "marin").strip(),
            realtime_instructions=os.getenv(
                "PYREALTIME_INSTRUCTIONS",
                "You are a concise and helpful realtime assistant.",
            ).strip(),
        )

    def session_config(self, *, tools: Sequence[Mapping[str, Any]] = ()) -> RealtimeSessionConfig:
        return RealtimeSessionConfig(
            model=self.realtime_model,
            voice=self.realtime_voice,
            instructions=self.realtime_instructions,
            tools=tools,
        )
