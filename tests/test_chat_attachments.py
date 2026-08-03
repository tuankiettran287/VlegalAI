from __future__ import annotations

import asyncio
import io
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from starlette.datastructures import UploadFile

from app.api import upload_chat_attachment
from app.core.config import Settings
from app.core.security import encrypt_text
from app.services.chat_attachments import (
    ChatAttachmentError,
    ExtractedChatAttachment,
    create_attachment_token,
    decode_attachment_token,
    extract_document_attachment,
    serialize_attachment_context,
    validate_chat_attachment,
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        session_secret="chat-attachment-test-secret",
    )


def test_chat_attachment_validates_magic_bytes_and_extracts_text() -> None:
    image = validate_chat_attachment(
        b"\x89PNG\r\n\x1a\n" + b"image-data",
        "bang-cham-cong.png",
        "application/octet-stream",
    )
    assert image.kind == "image"
    assert image.content_type == "image/png"
    assert image.requires_ocr is True

    document = validate_chat_attachment(
        "HỢP ĐỒNG LAO ĐỘNG\n\nĐiều 1. Công việc của người lao động.".encode(),
        "hop-dong.txt",
        "text/plain",
    )
    extracted = extract_document_attachment(document)
    assert extracted.kind == "document"
    assert "Điều 1" in extracted.text

    with pytest.raises(ChatAttachmentError, match="không khớp"):
        validate_chat_attachment(b"not-an-image", "fake.png", "image/png")


def test_attachment_token_is_user_bound_and_expiring() -> None:
    settings = _settings()
    attachment = ExtractedChatAttachment(
        filename="noi-quy.txt",
        content_type="text/plain",
        kind="document",
        size_bytes=120,
        text="Nội quy lao động và quy trình xử lý kỷ luật.",
        truncated=False,
    )
    token = create_attachment_token(attachment, "user-1", settings)
    decoded = decode_attachment_token(token, "user-1", settings)
    assert decoded["filename"] == "noi-quy.txt"
    assert "kỷ luật" in decoded["text"]

    with pytest.raises(ChatAttachmentError, match="không thuộc"):
        decode_attachment_token(token, "user-2", settings)

    expired_payload = attachment.token_payload("user-1")
    expired_payload["expires_at"] = (
        datetime.now(UTC) - timedelta(minutes=1)
    ).isoformat()
    expired_token = encrypt_text(
        json.dumps(expired_payload, ensure_ascii=False),
        settings,
    )
    with pytest.raises(ChatAttachmentError, match="hết hạn"):
        decode_attachment_token(expired_token, "user-1", settings)


def test_stored_attachment_context_excludes_token_identity_fields() -> None:
    value = serialize_attachment_context(
        [
            {
                "version": 1,
                "user_id": "private-user",
                "expires_at": datetime.now(UTC).isoformat(),
                "filename": "anh.jpg",
                "content_type": "image/jpeg",
                "kind": "image",
                "size_bytes": 42,
                "page_count": None,
                "truncated": False,
                "text": "Ca làm việc từ 22 giờ đến 06 giờ.",
            }
        ]
    )
    payload = json.loads(value)[0]
    assert "user_id" not in payload
    assert "expires_at" not in payload
    assert payload["filename"] == "anh.jpg"
    assert "22 giờ" in payload["text"]


def test_upload_endpoint_extracts_document_and_ocr_image() -> None:
    settings = _settings()
    user = SimpleNamespace(id="user-1")

    class _AI:
        calls: list[tuple[str, str]] = []

        async def extract_attachment_text(
            self,
            data: bytes,
            content_type: str,
            filename: str,
        ) -> str:
            assert data.startswith(b"\x89PNG")
            self.calls.append((content_type, filename))
            return "BẢNG CHẤM CÔNG\nCa đêm từ 22 giờ đến 06 giờ."

    ai = _AI()
    document = UploadFile(
        io.BytesIO("NỘI QUY LAO ĐỘNG\n\nĐiều 1. Thời giờ làm việc.".encode()),
        filename="noi-quy.txt",
    )
    document_result = asyncio.run(
        upload_chat_attachment(document, user, settings, ai)
    )
    assert document_result.kind == "document"
    assert "NỘI QUY" in document_result.preview
    assert ai.calls == []

    image = UploadFile(
        io.BytesIO(b"\x89PNG\r\n\x1a\nimage-data"),
        filename="bang-cham-cong.png",
    )
    image_result = asyncio.run(
        upload_chat_attachment(image, user, settings, ai)
    )
    assert image_result.kind == "image"
    assert "Ca đêm" in image_result.preview
    assert ai.calls == [("image/png", "bang-cham-cong.png")]
    decoded = decode_attachment_token(image_result.token, "user-1", settings)
    assert "22 giờ" in decoded["text"]
