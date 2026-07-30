from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import _feedback_question_similarity, _message_out, rate_chat_answer
from app.core.config import Settings
from app.core.security import decrypt_text, encrypt_text
from app.models import ChatAnswerFeedback, ChatMessage
from app.schemas import ChatAnswerFeedbackRequest


class _FeedbackDb:
    def __init__(
        self,
        answer: ChatMessage,
        question: ChatMessage,
    ) -> None:
        self.results: list[object | None] = [answer, question, None]
        self.added: list[object] = []
        self.committed = False

    async def scalar(self, _: object) -> object | None:
        return self.results.pop(0)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.committed = True


def _message(
    settings: Settings,
    *,
    conversation_id: uuid.UUID,
    sequence: int,
    role: str,
    content: str,
) -> ChatMessage:
    return ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        message_sequence=sequence,
        role=role,
        content_ciphertext=encrypt_text(content, settings),
        content_hash="hash",
        sources=[],
        verification={},
        status="COMPLETED",
        created_at=datetime.now(UTC),
    )


def test_good_feedback_is_encrypted_and_returned_with_message() -> None:
    settings = Settings(
        _env_file=None,
        session_secret="chat-feedback-test",
    )
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    question = _message(
        settings,
        conversation_id=conversation_id,
        sequence=1,
        role="USER",
        content="Tôi được nghỉ phép bao nhiêu ngày?",
    )
    answer = _message(
        settings,
        conversation_id=conversation_id,
        sequence=2,
        role="ASSISTANT",
        content="Người lao động được nghỉ hằng năm theo luật.",
    )
    db = _FeedbackDb(answer, question)

    result = asyncio.run(
        rate_chat_answer(
            answer.id,
            ChatAnswerFeedbackRequest(rating="good"),
            db=db,
            user=SimpleNamespace(id=user_id),
            settings=settings,
        )
    )

    feedback = next(
        item for item in db.added if isinstance(item, ChatAnswerFeedback)
    )
    assert result.rating == "good"
    assert result.regeneration_available is False
    assert feedback.rating == "GOOD"
    assert decrypt_text(feedback.question_ciphertext, settings).startswith(
        "Tôi được nghỉ phép"
    )
    assert decrypt_text(feedback.answer_ciphertext, settings).startswith(
        "Người lao động"
    )
    assert db.committed is True
    assert _message_out(answer, settings, "GOOD").feedback_rating == "good"


def test_bad_feedback_requires_an_explanation() -> None:
    settings = Settings(
        _env_file=None,
        session_secret="chat-feedback-test",
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            rate_chat_answer(
                uuid.uuid4(),
                ChatAnswerFeedbackRequest(rating="bad"),
                db=SimpleNamespace(),
                user=SimpleNamespace(id=uuid.uuid4()),
                settings=settings,
            )
        )

    assert exc_info.value.status_code == 422


def test_feedback_similarity_matches_related_questions_only() -> None:
    assert _feedback_question_similarity(
        "Cách tính tiền lương làm thêm ban đêm?",
        "Tiền lương tăng ca vào ban đêm được tính thế nào?",
    ) >= 0.4
    assert _feedback_question_similarity(
        "Cách tính tiền lương làm thêm ban đêm?",
        "Điều kiện thành lập doanh nghiệp là gì?",
    ) < 0.4
