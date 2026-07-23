from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.core.security import encrypt_text
from app.models import LegalAnswerCache
from app.services import semantic_cache
from app.services.semantic_cache import (
    CacheLookup,
    SemanticAnswerCacheService,
    is_public_cache_candidate,
    legal_fingerprint,
    normalize_public_query,
)


class _FakeEmbeddings:
    def embed_query(self, _: str) -> list[float]:
        raise AssertionError("Exact cache hits must not run embedding inference")


class _FakeSession:
    def __init__(self, exact: LegalAnswerCache | None = None) -> None:
        self.exact = exact
        self.statements: list[object] = []
        self.committed = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def scalar(self, _: object) -> LegalAnswerCache | None:
        return self.exact

    async def execute(self, statement: object) -> None:
        self.statements.append(statement)

    async def commit(self) -> None:
        self.committed = True


def test_privacy_gate_only_accepts_context_free_public_legal_questions() -> None:
    public = "Pháp luật quy định thời hạn khởi kiện tranh chấp lao động là bao lâu?"

    assert is_public_cache_candidate(public)
    assert normalize_public_query(public) == normalize_public_query(public.upper().rstrip("?"))
    assert not is_public_cache_candidate("Tôi bị công ty sa thải, quyền của tôi là gì?")
    assert not is_public_cache_candidate("Quy định áp dụng cho email an@example.com là gì?")

    service = SemanticAnswerCacheService(Settings(_env_file=None), _FakeEmbeddings())
    assert service.eligible(public, has_conversation_context=False)
    assert not service.eligible(public, has_conversation_context=True)


def test_law_fingerprint_ignores_check_time_but_tracks_legal_state() -> None:
    sources = [{"doc_id": "doc-1", "citation": "Điều 1", "source_url": "https://vbpl.vn/1"}]
    first = {
        "checked_at": "2026-01-01T00:00:00Z",
        "items": [{"code": "01/2026/QH", "status": "IN_FORCE", "source_url": "https://vbpl.vn/1"}],
    }
    later = {**first, "checked_at": "2026-02-01T00:00:00Z"}
    expired = {
        **later,
        "items": [{"code": "01/2026/QH", "status": "EXPIRED", "source_url": "https://vbpl.vn/1"}],
    }

    assert legal_fingerprint(sources, first) == legal_fingerprint(sources, later)
    assert legal_fingerprint(sources, first) != legal_fingerprint(sources, expired)


def test_exact_cache_hit_skips_embedding_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, session_secret="semantic-cache-test")
    query = "Pháp luật quy định thời hạn khởi kiện là bao lâu?"
    row = LegalAnswerCache(
        id=uuid.uuid4(),
        query_hash="unused-by-fake-session",
        query_ciphertext=encrypt_text(normalize_public_query(query), settings),
        answer_ciphertext=encrypt_text("Thời hạn là một năm.", settings),
        answer_hash="a" * 64,
        query_embedding=[0.0] * 1024,
        sources=[],
        verification={},
        law_fingerprint="b" * 64,
        model_name=settings.qwen_model,
        prompt_version="legal-answer-v1",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        hit_count=0,
    )
    db = _FakeSession(row)
    monkeypatch.setattr(semantic_cache, "SessionFactory", lambda: db)
    service = SemanticAnswerCacheService(settings, _FakeEmbeddings())

    lookup = asyncio.run(service.lookup(query))

    assert lookup.hit is not None
    assert lookup.hit.answer == "Thời hạn là một năm."
    assert lookup.hit.similarity == 1.0
    assert lookup.hit.exact_match


def test_store_uses_atomic_postgresql_upsert(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None, session_secret="semantic-cache-store-test")
    db = _FakeSession()
    monkeypatch.setattr(semantic_cache, "SessionFactory", lambda: db)
    service = SemanticAnswerCacheService(settings, _FakeEmbeddings())
    lookup = CacheLookup(
        query_hash="c" * 64,
        normalized_query="pháp luật quy định thời hạn",
        embedding=[0.25] * 1024,
        hit=None,
    )

    asyncio.run(
        service.store(
            lookup,
            "Câu trả lời công khai.",
            [{"doc_id": "doc-1", "citation": "Điều 1"}],
            {"checked": True, "all_current": True, "items": []},
        )
    )

    assert db.committed
    sql = str(db.statements[0].compile(dialect=postgresql.dialect()))
    assert "INSERT INTO legal_answer_cache" in sql
    assert "ON CONFLICT" in sql
