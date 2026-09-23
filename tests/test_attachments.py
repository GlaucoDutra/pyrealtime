import io

import pytest

from pyrealtime import AttachmentPolicy, AttachmentProcessor, AttachmentTooLargeError


def test_text_is_sanitized_chunked_and_truncated():
    processor = AttachmentProcessor(AttachmentPolicy(max_text_chars=8, chunk_chars=3))
    prepared = processor.prepare_sync("../unsafe/notes.txt", "text/plain", b"abcdefghij")

    assert prepared.filename == "notes.txt"
    assert prepared.kind == "text"
    assert prepared.chunks == ("abc", "def", "gh")
    assert prepared.truncated is True


def test_unsupported_file_returns_an_honest_notice():
    prepared = AttachmentProcessor().prepare_sync("archive.zip", "application/zip", b"not-a-real-zip")

    assert prepared.kind == "notice"
    assert "not supported" in (prepared.message or "")


def test_size_limit_is_enforced():
    processor = AttachmentProcessor(AttachmentPolicy(max_file_bytes=3))
    with pytest.raises(AttachmentTooLargeError):
        processor.prepare_sync("notes.txt", "text/plain", b"four")


def test_image_is_normalized_for_realtime():
    from PIL import Image

    source = io.BytesIO()
    Image.new("RGB", (40, 20), "blue").save(source, format="PNG")
    prepared = AttachmentProcessor().prepare_sync("photo.png", "image/png", source.getvalue())

    assert prepared.kind == "image"
    assert prepared.media_type == "image/jpeg"
    assert prepared.data_url and prepared.data_url.startswith("data:image/jpeg;base64,")
