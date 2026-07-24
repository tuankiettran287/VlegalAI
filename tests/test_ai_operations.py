from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.security import encrypt_text
from app.schemas import DraftContractRequest, VerificationItem, VerificationReport
from app.services import conversation_memory
from app.services.conversation_memory import ConversationMemoryService, _SummarySnapshot


class _Rows:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def all(self) -> list[object]:
        return self.rows


class _TrackedSession:
    def __init__(
        self,
        scalar_results: list[object],
        rows: list[object] | None = None,
    ) -> None:
        self.scalar_results = iter(scalar_results)
        self.rows = rows or []
        self.active = False
        self.executed: list[object] = []
        self.added: list[object] = []
        self.committed = False

    async def __aenter__(self) -> _TrackedSession:
        self.active = True
        return self

    async def __aexit__(self, *_: object) -> None:
        self.active = False

    async def execute(self, statement: object, *_: object) -> None:
        self.executed.append(statement)

    async def scalar(self, _: object) -> object:
        return next(self.scalar_results)

    async def scalars(self, _: object) -> _Rows:
        return _Rows(self.rows)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, _: object) -> None:
        return None


class _CheckingAI:
    def __init__(self, sessions: list[_TrackedSession]) -> None:
        self.sessions = sessions
        self.calls = 0

    async def complete(self, *_: object, **__: object) -> str:
        assert not any(session.active for session in self.sessions)
        self.calls += 1
        return "Tóm tắt đã cập nhật."


class _CheckingEmbeddings:
    def __init__(self, sessions: list[_TrackedSession]) -> None:
        self.sessions = sessions
        self.calls = 0

    def embed_documents(self, _: list[str]) -> list[list[float]]:
        assert not any(session.active for session in self.sessions)
        self.calls += 1
        return [[0.25] * 1024]


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        session_secret="ai-operations-test",
        conversation_summary_batch_size=12,
    )


def test_memory_releases_read_session_before_ai_and_locks_only_for_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    conversation_id = uuid.uuid4()
    now = datetime.now(UTC)
    messages = [
        SimpleNamespace(
            role="USER",
            message_sequence=1,
            content_ciphertext=encrypt_text("Câu hỏi", settings),
            created_at=now,
            id=uuid.uuid4(),
        ),
        SimpleNamespace(
            role="ASSISTANT",
            message_sequence=2,
            content_ciphertext=encrypt_text("Câu trả lời", settings),
            created_at=now + timedelta(seconds=1),
            id=uuid.uuid4(),
        ),
    ]
    read_db = _TrackedSession([conversation_id, None], messages)
    write_db = _TrackedSession([conversation_id, None])
    sessions = [read_db, write_db]
    session_iter = iter(sessions)
    monkeypatch.setattr(
        conversation_memory,
        "SessionFactory",
        lambda: next(session_iter),
    )
    ai = _CheckingAI(sessions)
    embeddings = _CheckingEmbeddings(sessions)

    memory = asyncio.run(
        ConversationMemoryService(settings, ai, embeddings).refresh(conversation_id)
    )

    assert memory is not None
    assert memory.source_message_count == 2
    assert memory.last_message_sequence == 2
    assert ai.calls == 1
    assert embeddings.calls == 1
    assert read_db.executed == []
    assert "pg_advisory_xact_lock" in str(write_db.executed[0])
    assert write_db.committed
    assert not any(session.active for session in sessions)


def test_memory_persist_detects_stale_snapshot_without_overwrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    conversation_id = uuid.uuid4()
    current = SimpleNamespace(
        source_message_count=1,
        last_message_sequence=1,
        summary_ciphertext="winner",
        summary_hash="winner-hash",
        embedding_model="winner-model",
        embedding_revision="winner-revision",
        embedding=[0.75] * 1024,
    )
    write_db = _TrackedSession([conversation_id, current])
    monkeypatch.setattr(conversation_memory, "SessionFactory", lambda: write_db)
    service = ConversationMemoryService(
        settings,
        SimpleNamespace(),
        SimpleNamespace(),
    )
    snapshot = _SummarySnapshot(
        base_count=0,
        target_count=2,
        base_sequence=0,
        target_sequence=2,
        summary="old",
        messages=(("USER", "one"), ("USER", "two")),
    )

    memory, conflict = asyncio.run(
        service._persist_snapshot(
            conversation_id,
            snapshot,
            "stale generated summary",
            [0.25] * 1024,
        )
    )

    assert memory is current
    assert conflict is True
    assert current.summary_ciphertext == "winner"
    assert current.source_message_count == 1
    assert not write_db.committed
    assert write_db.added == []


def test_memory_retries_from_winning_summary_after_cas_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    conversation_id = uuid.uuid4()
    service = ConversationMemoryService(
        settings,
        SimpleNamespace(),
        SimpleNamespace(),
    )
    first = _SummarySnapshot(
        base_count=0,
        target_count=2,
        base_sequence=0,
        target_sequence=2,
        summary="empty",
        messages=(("USER", "one"), ("USER", "two")),
    )
    second = _SummarySnapshot(
        base_count=1,
        target_count=2,
        base_sequence=1,
        target_sequence=2,
        summary="winner summary for one",
        messages=(("USER", "two"),),
    )
    snapshots = iter(
        [
            (first, None),
            (
                second,
                SimpleNamespace(source_message_count=1, last_message_sequence=1),
            ),
        ]
    )
    ai_inputs: list[str] = []
    persist_counts: list[tuple[int, int]] = []
    final_memory = SimpleNamespace(source_message_count=2, last_message_sequence=2)

    async def read_snapshot(_: uuid.UUID) -> tuple[object, object]:
        return next(snapshots)

    async def complete(_: object, prompt: str, **__: object) -> str:
        ai_inputs.append(prompt)
        return f"summary-{len(ai_inputs)}"

    def embed(_: list[str]) -> list[list[float]]:
        return [[0.5] * 1024]

    async def persist_snapshot(
        _: uuid.UUID,
        snapshot: _SummarySnapshot,
        __: str,
        ___: list[float],
    ) -> tuple[object, bool]:
        persist_counts.append((snapshot.base_count, snapshot.target_count))
        if len(persist_counts) == 1:
            return SimpleNamespace(
                source_message_count=1,
                last_message_sequence=1,
            ), True
        return final_memory, False

    monkeypatch.setattr(service, "_read_snapshot", read_snapshot)
    monkeypatch.setattr(service, "_persist_snapshot", persist_snapshot)
    service.ai = SimpleNamespace(complete=complete)
    service.embeddings = SimpleNamespace(embed_documents=embed)

    memory = asyncio.run(service.refresh(conversation_id))

    assert memory is final_memory
    assert persist_counts == [(0, 2), (1, 2)]
    assert len(ai_inputs) == 2
    assert "winner summary for one" in ai_inputs[1]
    assert "two" in ai_inputs[1]


def test_worker_logs_document_failure_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app import worker

    documents = [
        SimpleNamespace(
            id=uuid.uuid4(),
            external_doc_id="bad-document",
            title="Bad",
            code="BAD",
        ),
        SimpleNamespace(
            id=uuid.uuid4(),
            external_doc_id="good-document",
            title="Good",
            code="GOOD",
        ),
    ]

    class _WorkerSession:
        async def __aenter__(self) -> _WorkerSession:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def scalars(self, _: object) -> _Rows:
            return _Rows(documents)

    class _WorkerAI:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class _Freshness:
        def __init__(self, *_: object) -> None:
            self.calls: list[str] = []

        async def verify_sources(
            self,
            sources: list[dict[str, object]],
        ) -> tuple[object, bool]:
            doc_id = str(sources[0]["doc_id"])
            self.calls.append(doc_id)
            if doc_id == "bad-document":
                raise RuntimeError("provider failed")
            return SimpleNamespace(), True

    ai = _WorkerAI()
    freshness = _Freshness()
    monkeypatch.setattr(worker, "SessionFactory", _WorkerSession)
    monkeypatch.setattr(worker, "GeminiService", lambda _: ai)
    monkeypatch.setattr(worker, "TavilyService", lambda _: SimpleNamespace())
    monkeypatch.setattr(
        worker,
        "GoogleSearchService",
        lambda *_: SimpleNamespace(),
    )
    monkeypatch.setattr(worker, "LegalIndexer", lambda _: SimpleNamespace())
    monkeypatch.setattr(worker, "LegalFreshnessService", lambda *_: freshness)

    with caplog.at_level(logging.ERROR, logger="app.worker"):
        result = asyncio.run(worker._verify_corpus())

    assert result == {"checked": 1, "updated": 1, "failed": 1}
    assert freshness.calls == ["bad-document", "good-document"]
    assert ai.closed
    records = [
        record
        for record in caplog.records
        if "Legal freshness verification failed" in record.getMessage()
    ]
    assert len(records) == 1
    assert str(documents[0].id) in records[0].getMessage()
    assert records[0].exc_info is not None


def test_worker_closes_ai_when_later_dependency_construction_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import worker

    class _WorkerAI:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    ai = _WorkerAI()
    monkeypatch.setattr(worker, "GeminiService", lambda _: ai)

    def fail_tavily(_: object) -> object:
        raise RuntimeError("tavily constructor failed")

    monkeypatch.setattr(worker, "TavilyService", fail_tavily)

    with pytest.raises(RuntimeError, match="tavily constructor failed"):
        asyncio.run(worker._verify_corpus())

    assert ai.closed


def test_contract_draft_releases_auth_transaction_before_external_calls() -> None:
    from app.api import draft_contract

    user_id = uuid.uuid4()

    class _Db:
        def __init__(self) -> None:
            self.active = True
            self.added: list[object] = []
            self.committed = False

        async def rollback(self) -> None:
            self.active = False

        async def scalar(self, _: object) -> object:
            assert not self.active
            self.active = True
            return user_id

        def add(self, value: object) -> None:
            self.added.append(value)

        async def commit(self) -> None:
            self.committed = True

        async def refresh(self, value: object) -> None:
            if getattr(value, "id", None) is None:
                value.id = uuid.uuid4()

    db = _Db()
    source = {
        "doc_id": "law-1",
        "title": "Luật thử nghiệm",
        "citation": "100/2020/QH14",
        "text": "Nội dung pháp lý đã được kiểm chứng.",
    }

    class _Retrieval:
        async def retrieve(self, _: str) -> list[dict[str, object]]:
            assert not db.active
            return [dict(source)]

    class _Freshness:
        async def verify_sources(
            self,
            _: list[dict[str, object]],
        ) -> tuple[VerificationReport, bool]:
            assert not db.active
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
        async def complete(self, *_: object, **__: object) -> str:
            assert not db.active
            return "Các bên phải thực hiện nghĩa vụ đúng thời hạn [S1]."

    result = asyncio.run(
        draft_contract(
            DraftContractRequest(
                prompt="Soạn hợp đồng dịch vụ thử nghiệm.",
                template_name="Hợp đồng dịch vụ",
            ),
            db,
            SimpleNamespace(id=user_id),
            _settings(),
            _Retrieval(),
            _Freshness(),
            _AI(),
        )
    )

    assert db.committed
    assert db.added
    assert result["draft"].endswith("[S1].")
