from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.api import chat
from app.core.config import Settings
from app.core.security import decrypt_text, encrypt_text
from app.models import ChatAnswerFeedback, ChatMessage, Conversation
from app.schemas import ChatRequest, VerificationItem, VerificationReport
from app.services.chat_attachments import (
    ExtractedChatAttachment,
    create_attachment_token,
    deserialize_attachment_context,
)


class _Rows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class _ChatSession:
    def __init__(self, conversation: Conversation) -> None:
        self.conversation = conversation
        self.scalar_calls = 0
        self.rolled_back = False
        self.lock_acquired = False
        self.added: list[object] = []
        self.committed = False

    async def scalar(self, _: object) -> object:
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return self.conversation
        if self.scalar_calls == 2:
            assert self.lock_acquired
            return self.conversation
        if self.scalar_calls == 3:
            assert self.lock_acquired
            return 4
        raise AssertionError("Unexpected scalar query")

    async def scalars(self, _: object) -> _Rows:
        return _Rows([])

    async def rollback(self) -> None:
        self.rolled_back = True

    async def execute(self, statement: object, *_: object) -> None:
        assert "pg_advisory_xact_lock" in str(statement)
        self.lock_acquired = True

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, value: object) -> None:
        if isinstance(value, ChatMessage) and value.id is None:
            value.id = uuid.uuid4()


class _Memory:
    def __init__(self, db: _ChatSession) -> None:
        self.db = db
        self.refreshed: list[uuid.UUID] = []

    async def get_summary(self, *_: object) -> str:
        return ""

    async def refresh(self, conversation_id: uuid.UUID) -> None:
        assert self.db.committed
        self.refreshed.append(conversation_id)


class _Retrieval:
    def __init__(self, db: _ChatSession) -> None:
        self.db = db

    async def retrieve(self, _: str) -> list[dict[str, object]]:
        assert self.db.rolled_back
        return [
            {
                "source_id": "S1",
                "score": 1.0,
                "chunk_type": "ARTICLE",
                "citation": "Điều 1 Luật thử nghiệm 100/2020/QH14",
                "title": "Luật thử nghiệm",
                "text": "Nội dung nguồn pháp lý.",
                "reasons": [],
                "doc_id": None,
                "source_url": "https://vanban.chinhphu.vn/example",
            }
        ]


class _Freshness:
    def __init__(self, db: _ChatSession) -> None:
        self.db = db

    async def verify_sources(
        self,
        _: list[dict[str, object]],
    ) -> tuple[VerificationReport, bool]:
        assert self.db.rolled_back
        return VerificationReport(
            checked=True,
            all_current=True,
            checked_at=datetime.now(UTC),
            items=[
                VerificationItem(
                    code="100/2020/QH14",
                    title="Luật thử nghiệm",
                    status="IN_FORCE",
                    checked_at=datetime.now(UTC),
                )
            ],
        ), False


class _AI:
    def __init__(self, db: _ChatSession) -> None:
        self.db = db
        self.prompts: list[str] = []

    async def complete(self, *args: object, **__: object) -> str:
        assert self.db.rolled_back
        if len(args) > 1:
            self.prompts.append(str(args[1]))
        return (
            "Theo Điều 1, Luật thử nghiệm số 100/2020/QH14 [S1], "
            "đây là quy định pháp luật thử nghiệm."
        )

    async def complete_json(self, *_: object, **__: object) -> dict:
        assert self.db.rolled_back
        return {
            "statements": [
                {
                    "text": "Đây là quy định pháp luật thử nghiệm.",
                    "citations": ["S1"],
                }
            ]
        }


class _Cache:
    @staticmethod
    def eligible(*_: object, **__: object) -> bool:
        return False


def test_authenticated_chat_reopens_write_transaction_and_appends_sequences() -> None:
    settings = Settings(_env_file=None, session_secret="chat-sequence-test")
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    conversation = Conversation(id=conversation_id, user_id=user_id)
    db = _ChatSession(conversation)
    memory = _Memory(db)

    result = asyncio.run(
        chat(
            ChatRequest(
                message="Quy định pháp luật thử nghiệm là gì?",
                conversation_id=conversation_id,
            ),
            db=db,
            user=SimpleNamespace(id=user_id, preferred_name="Minh"),
            settings=settings,
            retrieval=_Retrieval(db),
            freshness=_Freshness(db),
            ai=_AI(db),
            memory=memory,
            answer_cache=_Cache(),
        )
    )

    messages = [value for value in db.added if isinstance(value, ChatMessage)]
    assert db.rolled_back
    assert db.lock_acquired
    assert db.committed
    assert [message.message_sequence for message in messages] == [5, 6]
    assert result.conversation_id == conversation_id
    # Fast single-hop turns do not synchronously refresh the long-term summary.
    assert memory.refreshed == []
    assert "Căn cứ được trích dẫn:" not in result.answer


def test_chat_uses_and_persists_encrypted_attachment_context() -> None:
    settings = Settings(_env_file=None, session_secret="chat-attachment-sequence-test")
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    conversation = Conversation(id=conversation_id, user_id=user_id)
    db = _ChatSession(conversation)
    memory = _Memory(db)
    ai = _AI(db)
    token = create_attachment_token(
        ExtractedChatAttachment(
            filename="noi-quy-lao-dong.txt",
            content_type="text/plain",
            kind="document",
            size_bytes=180,
            text="Điều 5. Người lao động làm việc từ 22 giờ đến 06 giờ.",
            truncated=False,
        ),
        str(user_id),
        settings,
    )

    asyncio.run(
        chat(
            ChatRequest(
                message="Quy định trong tệp này có phù hợp không?",
                conversation_id=conversation_id,
                attachments=[{"token": token}],
            ),
            db=db,
            user=SimpleNamespace(id=user_id, preferred_name="Minh"),
            settings=settings,
            retrieval=_Retrieval(db),
            freshness=_Freshness(db),
            ai=ai,
            memory=memory,
            answer_cache=_Cache(),
        )
    )

    user_message = next(
        item
        for item in db.added
        if isinstance(item, ChatMessage) and item.role == "USER"
    )
    assert user_message.attachments[0]["filename"] == "noi-quy-lao-dong.txt"
    assert user_message.attachment_context_ciphertext is not None
    stored = deserialize_attachment_context(
        decrypt_text(user_message.attachment_context_ciphertext, settings)
    )
    assert "22 giờ" in stored[0]["text"]
    assert any("USER_ATTACHMENTS" in prompt and "22 giờ" in prompt for prompt in ai.prompts)


class _RegenerationSession:
    def __init__(
        self,
        conversation: Conversation,
        question: ChatMessage,
        answer: ChatMessage,
        feedback: ChatAnswerFeedback,
    ) -> None:
        self.results: list[object] = [
            conversation,
            answer,
            question,
            feedback,
            conversation,
            4,
            answer,
            feedback,
        ]
        self.rolled_back = False
        self.lock_acquired = False
        self.added: list[object] = []
        self.executed_sql: list[str] = []
        self.committed = False

    async def scalar(self, _: object) -> object:
        return self.results.pop(0)

    async def scalars(self, _: object) -> _Rows:
        return _Rows([])

    async def rollback(self) -> None:
        self.rolled_back = True

    async def execute(self, statement: object, *_: object) -> None:
        sql = str(statement)
        self.executed_sql.append(sql)
        if "pg_advisory_xact_lock" in sql:
            self.lock_acquired = True

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _: object) -> None:
        return None


def test_bad_feedback_regenerates_without_duplicating_the_user_question() -> None:
    settings = Settings(
        _env_file=None,
        session_secret="chat-regeneration-test",
    )
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    conversation = Conversation(id=conversation_id, user_id=user_id)
    question = ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        message_sequence=3,
        role="USER",
        content_ciphertext=encrypt_text(
            "Quy định pháp luật thử nghiệm là gì?",
            settings,
        ),
        content_hash="question-hash",
        status="COMPLETED",
    )
    answer = ChatMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        message_sequence=4,
        role="ASSISTANT",
        content_ciphertext=encrypt_text(
            "Câu trả lời cũ còn thiếu ví dụ.",
            settings,
        ),
        content_hash="answer-hash",
        status="COMPLETED",
    )
    feedback = ChatAnswerFeedback(
        id=uuid.uuid4(),
        user_id=user_id,
        conversation_id=conversation_id,
        message_id=answer.id,
        rating="BAD",
        comment_ciphertext=encrypt_text(
            "Hãy bổ sung ví dụ dễ hiểu.",
            settings,
        ),
        question_ciphertext=question.content_ciphertext,
        answer_ciphertext=answer.content_ciphertext,
    )
    db = _RegenerationSession(
        conversation,
        question,
        answer,
        feedback,
    )

    result = asyncio.run(
        chat(
            ChatRequest(
                message="Nội dung này không được dùng thay câu hỏi gốc",
                conversation_id=conversation_id,
                regenerate_from_message_id=answer.id,
            ),
            db=db,
            user=SimpleNamespace(id=user_id, preferred_name="Minh"),
            settings=settings,
            retrieval=_Retrieval(db),  # type: ignore[arg-type]
            freshness=_Freshness(db),  # type: ignore[arg-type]
            ai=_AI(db),  # type: ignore[arg-type]
            memory=_Memory(db),  # type: ignore[arg-type]
            answer_cache=_Cache(),
        )
    )

    persisted = [
        item for item in db.added if isinstance(item, ChatMessage)
    ]
    assert len(persisted) == 1
    assert persisted[0].role == "ASSISTANT"
    assert persisted[0].message_sequence == 5
    assert answer.status == "SUPERSEDED"
    assert feedback.regenerated_message_id == result.message_id
    assert result.replaces_message_id == answer.id
    assert any(
        "DELETE FROM conversation_summary" in sql
        for sql in db.executed_sql
    )
