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
