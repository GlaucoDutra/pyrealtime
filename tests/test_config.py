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
    settings = ServerSettings.from_env()

    assert settings.tool_model == "gpt-5-mini"
    assert settings.image_model == "gpt-image-2.5-flare"
    assert settings.vector_store_ids == ("vs_one", "vs_two")
