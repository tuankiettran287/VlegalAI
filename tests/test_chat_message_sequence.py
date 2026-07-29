from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import BackgroundTasks, Response

from app.api import chat
from app.core.config import Settings
from app.models import ChatMessage, Conversation
from app.schemas import ChatRequest, VerificationItem, VerificationReport


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

    async def complete(self, *_: object, **__: object) -> str:
        assert self.db.rolled_back
        return (
            "Theo Điều 1, Luật thử nghiệm số 100/2020/QH14 [S1], "
            "đây là quy định pháp luật thử nghiệm."
        )


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
    background_tasks = BackgroundTasks()

    result = asyncio.run(
        chat(
            ChatRequest(
                message="Quy định pháp luật thử nghiệm là gì?",
                conversation_id=conversation_id,
            ),
            SimpleNamespace(),
            Response(),
            background_tasks,
            db,
            SimpleNamespace(id=user_id),
            settings,
            _Retrieval(db),
            _Freshness(db),
            _AI(db),
            SimpleNamespace(),
            memory,
            _Cache(),
        )
    )

    messages = [value for value in db.added if isinstance(value, ChatMessage)]
    assert db.rolled_back
    assert db.lock_acquired
    assert db.committed
    assert [message.message_sequence for message in messages] == [5, 6]
    assert result.conversation_id == conversation_id
    assert memory.refreshed == []

    asyncio.run(background_tasks())

    assert memory.refreshed == [conversation_id]
