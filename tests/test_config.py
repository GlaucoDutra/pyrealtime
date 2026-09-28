import pytest

from pyrealtime import RealtimeSessionConfig


def test_session_payload_contains_audio_vad_and_transcription():
    config = RealtimeSessionConfig(instructions="Be concise.")
    session = config.to_session()

    assert session["type"] == "realtime"
    assert session["model"] == "gpt-realtime-2.1-mini"
    assert session["audio"]["output"]["voice"] == "marin"
    assert session["audio"]["input"]["transcription"]["model"] == "gpt-4o-mini-transcribe"
    assert session["audio"]["input"]["turn_detection"]["interrupt_response"] is True
    assert config.to_client_secret_payload() == {"session": session}


def test_invalid_vad_threshold_is_rejected():
    with pytest.raises(ValueError, match="vad_threshold"):
        RealtimeSessionConfig(vad_threshold=1.1)


def test_server_settings_load_hosted_tool_configuration(monkeypatch):
    from pyrealtime import ServerSettings

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("PYREALTIME_VECTOR_STORE_IDS", "vs_one, vs_two")
    monkeypatch.setenv("PYREALTIME_CHAT_RATE_LIMIT", "12")
    monkeypatch.setenv("PYREALTIME_MAX_CHAT_HISTORY_MESSAGES", "8")
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test")
    monkeypatch.setenv("PYREALTIME_JEV_MAX_QUESTIONS", "7")
    settings = ServerSettings.from_env()

    assert settings.tool_model == "gpt-5-mini"
    assert settings.tool_timeout_seconds == 120.0
    assert settings.image_model == "gpt-image-2.5-flare"
    assert settings.vector_store_ids == ("vs_one", "vs_two")
    assert settings.chat_model == "gpt-5-mini"
    assert settings.chat_rate_limit == 12
    assert settings.max_chat_history_messages == 8
    assert settings.typesafe_api_key == "ts-test"
    assert settings.jev_limits().max_questions == 7
