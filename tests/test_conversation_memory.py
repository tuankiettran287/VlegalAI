from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.security import decrypt_text, encrypt_text
from app.services import conversation_memory
from app.services.conversation_memory import ConversationMemoryService


class _Rows:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self.rows


class _FakeSession:
    def __init__(self, scalar_results: list[object], messages: list[SimpleNamespace]) -> None:
        self.scalar_results = iter(scalar_results)
        self.messages = messages
        self.executed: list[object] = []
        self.added: list[object] = []
        self.committed = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, statement: object, *_: object) -> None:
        self.executed.append(statement)

    async def scalar(self, _: object) -> object:
        return next(self.scalar_results)

    async def scalars(self, _: object) -> _Rows:
        return _Rows(self.messages)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _: object) -> None:
        return None


class _FakeAI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    async def complete(self, system: str, user: str, **kwargs: object) -> str:
        self.calls.append((system, user, kwargs))
        return "Người dùng hỏi về thời hạn; trợ lý kết luận là 30 ngày."


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.inputs: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.inputs.append(texts)
        return [[0.5] * 1024]


def test_refresh_summarizes_embeds_and_persists_conversation_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        session_secret="conversation-memory-test",
        conversation_summary_batch_size=12,
    )
    conversation_id = uuid.uuid4()
    now = datetime.now(UTC)
    messages = [
        SimpleNamespace(
            id=uuid.uuid4(),
            role="USER",
            content_ciphertext=encrypt_text("Thời hạn là bao lâu?", settings),
            created_at=now,
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            role="ASSISTANT",
            content_ciphertext=encrypt_text("Thời hạn là 30 ngày.", settings),
            created_at=now + timedelta(seconds=1),
        ),
    ]
    db = _FakeSession([conversation_id, None, 2], messages)
    monkeypatch.setattr(conversation_memory, "SessionFactory", lambda: db)
    ai = _FakeAI()
    embeddings = _FakeEmbeddings()
    service = ConversationMemoryService(settings, ai, embeddings)

    memory = asyncio.run(service.refresh(conversation_id))

    assert memory is not None
    assert db.committed
    assert db.added == [memory]
    assert "pg_advisory_xact_lock" in str(db.executed[0])
    assert "Thời hạn là bao lâu?" in ai.calls[0][1]
    assert embeddings.inputs == [[
        "Người dùng hỏi về thời hạn; trợ lý kết luận là 30 ngày."
    ]]
    assert memory.source_message_count == 2
    assert memory.embedding == [0.5] * 1024
    assert memory.embedding_model == settings.embedding_model_repo
    assert decrypt_text(memory.summary_ciphertext, settings).startswith("Người dùng hỏi")
