from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.api import _message_out
from app.core.config import Settings
from app.core.security import encrypt_text
from app.models import ChatMessage


def _stored_message(
    settings: Settings,
    *,
    verification: object,
    sources: object | None = None,
    content_ciphertext: str | None = None,
) -> ChatMessage:
    return ChatMessage(
        id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        message_sequence=1,
        role="ASSISTANT",
        content_ciphertext=content_ciphertext or encrypt_text("Nội dung lịch sử", settings),
        content_hash="history-hash",
        sources=sources if sources is not None else [],
        verification=verification,
        token_count=0,
        status="COMPLETED",
        created_at=datetime.now(UTC),
    )


def test_stored_message_with_empty_verification_has_a_safe_response_contract() -> None:
    settings = Settings(_env_file=None, session_secret="conversation-detail-test")
    message = _stored_message(settings, verification={})

    result = _message_out(message, settings)

    assert result.content == "Nội dung lịch sử"
    assert result.role == "assistant"
    assert result.sources == []
    assert result.verification is None


def test_stored_message_normalizes_legacy_and_malformed_metadata() -> None:
    settings = Settings(_env_file=None, session_secret="conversation-detail-test")
    message = _stored_message(
        settings,
        verification={
            "checked": True,
            "all_current": True,
            "items": None,
            "note": "Đã kiểm tra dữ liệu cũ.",
        },
        sources=[
            {
                "source_id": "S1",
                "citation": "Điều 1",
                "title": "Luật thử nghiệm",
                "text": "Nội dung nguồn",
                "reasons": [],
            },
            "invalid-source",
        ],
    )

    result = _message_out(message, settings)

    assert result.verification is not None
    assert result.verification.checked is True
    assert result.verification.items == []
    assert result.verification.note == "Đã kiểm tra dữ liệu cũ."
    assert [source.source_id for source in result.sources] == ["S1"]


def test_stored_message_with_unreadable_ciphertext_does_not_break_conversation() -> None:
    settings = Settings(_env_file=None, session_secret="conversation-detail-test")
    message = _stored_message(
        settings,
        verification={},
        content_ciphertext="not-valid-ciphertext",
    )

    result = _message_out(message, settings)

    assert result.content == "Không thể khôi phục nội dung tin nhắn này."
