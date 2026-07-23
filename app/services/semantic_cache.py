from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.config import Settings
from app.core.security import decrypt_text, encrypt_text
from app.db import SessionFactory
from app.models import LegalAnswerCache
from app.services.embeddings import EmbeddingConfig, LocalEmbeddingService, get_embedding_service


LEGAL_ANSWER_PROMPT_VERSION = "legal-answer-v1"
_PRIVATE_CONTEXT_RE = re.compile(
    r"\b("
    r"tôi|mình|chúng tôi|của tôi|của mình|công ty tôi|gia đình tôi|"
    r"vợ tôi|chồng tôi|con tôi|nhà tôi|hợp đồng của|vụ việc của|"
    r"địa chỉ|cccd|cmnd|căn cước|số điện thoại|email của|mã số thuế của"
    r")\b",
    re.IGNORECASE,
)
_DIRECT_IDENTIFIER_RE = re.compile(
    r"(?:https?://|www\.|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b\d{6,}\b)",
    re.IGNORECASE,
)
_PUBLIC_LEGAL_RE = re.compile(
    r"\b("
    r"pháp luật|quy định|bộ luật|luật|nghị định|thông tư|điều kiện|"
    r"thủ tục|hồ sơ|thời hạn|mức phạt|xử phạt|cơ quan|nghĩa vụ|"
    r"quyền|được phép|hiệu lực"
    r")\b",
    re.IGNORECASE,
)


def normalize_public_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", query).casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return re.sub(r"[\s?!.,;:]+$", "", normalized)


def is_public_cache_candidate(query: str, *, max_chars: int = 1500) -> bool:
    normalized = normalize_public_query(query)
    return (
        20 <= len(normalized) <= max_chars
        and bool(_PUBLIC_LEGAL_RE.search(normalized))
        and not _PRIVATE_CONTEXT_RE.search(normalized)
        and not _DIRECT_IDENTIFIER_RE.search(normalized)
    )


def legal_fingerprint(
    sources: list[dict[str, Any]],
    verification: dict[str, Any],
) -> str:
    source_identity = sorted(
        {
            (
                str(source.get("doc_id") or ""),
                str(source.get("citation") or ""),
                str(source.get("source_url") or ""),
            )
            for source in sources
        }
    )
    verification_identity = sorted(
        {
            (
                str(item.get("code") or ""),
                str(item.get("status") or ""),
                str(item.get("replacement_code") or ""),
                str(item.get("source_url") or ""),
            )
            for item in verification.get("items", [])
        }
    )
    canonical = json.dumps(
        {
            "sources": source_identity,
            "verification": verification_identity,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _embedding_config(settings: Settings) -> EmbeddingConfig:
    return EmbeddingConfig(
        model_path=settings.embedding_model_path,
        model_repo=settings.embedding_model_repo,
        model_revision=settings.embedding_model_revision,
        device=settings.embedding_device,
        dimensions=settings.postgres_vector_size,
        batch_size=settings.embedding_batch_size,
        max_sequence_length=settings.embedding_max_sequence_length,
    )


@dataclass(frozen=True, slots=True)
class CachedLegalAnswer:
    id: uuid.UUID
    answer: str
    sources: list[dict[str, Any]]
    verification: dict[str, Any]
    law_fingerprint: str
    similarity: float
    exact_match: bool


@dataclass(frozen=True, slots=True)
class CacheLookup:
    query_hash: str
    normalized_query: str
    embedding: list[float] | None
    hit: CachedLegalAnswer | None


class SemanticAnswerCacheService:
    """Cross-user cache restricted to context-free public legal questions."""

    def __init__(
        self,
        settings: Settings,
        embeddings: LocalEmbeddingService | None = None,
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings or get_embedding_service(_embedding_config(settings))

    def eligible(self, query: str, *, has_conversation_context: bool) -> bool:
        return (
            self.settings.semantic_answer_cache_enabled
            and not has_conversation_context
            and is_public_cache_candidate(
                query,
                max_chars=self.settings.semantic_answer_cache_max_query_chars,
            )
        )

    def _cached_answer(
        self,
        row: LegalAnswerCache,
        similarity: float,
        *,
        exact_match: bool,
    ) -> CachedLegalAnswer:
        return CachedLegalAnswer(
            id=row.id,
            answer=decrypt_text(row.answer_ciphertext, self.settings),
            sources=list(row.sources),
            verification=dict(row.verification),
            law_fingerprint=row.law_fingerprint,
            similarity=similarity,
            exact_match=exact_match,
        )

    async def lookup(self, query: str) -> CacheLookup:
        normalized_query = normalize_public_query(query)
        query_hash = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        active = (
            LegalAnswerCache.expires_at > now,
            LegalAnswerCache.model_name == self.settings.qwen_model,
            LegalAnswerCache.prompt_version == LEGAL_ANSWER_PROMPT_VERSION,
        )
        async with SessionFactory() as db:
            exact = await db.scalar(
                select(LegalAnswerCache).where(
                    LegalAnswerCache.query_hash == query_hash,
                    *active,
                )
            )
            if exact:
                return CacheLookup(
                    query_hash=query_hash,
                    normalized_query=normalized_query,
                    embedding=None,
                    hit=self._cached_answer(exact, 1.0, exact_match=True),
                )

        embedding = await run_in_threadpool(self.embeddings.embed_query, normalized_query)
        distance = LegalAnswerCache.query_embedding.cosine_distance(embedding)
        async with SessionFactory() as db:
            result = await db.execute(
                select(LegalAnswerCache, distance.label("distance"))
                .where(*active)
                .order_by(distance)
                .limit(1)
            )
            match = result.first()
        hit = None
        if match:
            similarity = 1.0 - float(match[1])
            if similarity >= self.settings.semantic_answer_cache_similarity:
                hit = self._cached_answer(match[0], similarity, exact_match=False)
        return CacheLookup(
            query_hash=query_hash,
            normalized_query=normalized_query,
            embedding=embedding,
            hit=hit,
        )

    async def store(
        self,
        lookup: CacheLookup,
        answer: str,
        sources: list[dict[str, Any]],
        verification: dict[str, Any],
    ) -> None:
        embedding = lookup.embedding
        if embedding is None:
            embedding = await run_in_threadpool(
                self.embeddings.embed_query,
                lookup.normalized_query,
            )
        now = datetime.now(UTC)
        values = {
            "id": uuid.uuid4(),
            "query_hash": lookup.query_hash,
            "query_ciphertext": encrypt_text(lookup.normalized_query, self.settings),
            "answer_ciphertext": encrypt_text(answer, self.settings),
            "answer_hash": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            "query_embedding": embedding,
            "sources": sources,
            "verification": verification,
            "law_fingerprint": legal_fingerprint(sources, verification),
            "model_name": self.settings.qwen_model,
            "prompt_version": LEGAL_ANSWER_PROMPT_VERSION,
            "expires_at": now + timedelta(hours=self.settings.semantic_answer_cache_ttl_hours),
            "hit_count": 0,
        }
        statement = insert(LegalAnswerCache).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[LegalAnswerCache.query_hash],
            set_={
                "query_ciphertext": statement.excluded.query_ciphertext,
                "answer_ciphertext": statement.excluded.answer_ciphertext,
                "answer_hash": statement.excluded.answer_hash,
                "query_embedding": statement.excluded.query_embedding,
                "sources": statement.excluded.sources,
                "verification": statement.excluded.verification,
                "law_fingerprint": statement.excluded.law_fingerprint,
                "model_name": statement.excluded.model_name,
                "prompt_version": statement.excluded.prompt_version,
                "expires_at": statement.excluded.expires_at,
                "updated_at": func.now(),
            },
        )
        async with SessionFactory() as db:
            await db.execute(statement)
            await db.execute(
                delete(LegalAnswerCache).where(
                    LegalAnswerCache.expires_at < now - timedelta(days=7)
                )
            )
            await db.commit()

    async def record_hit(self, cache_id: uuid.UUID) -> None:
        async with SessionFactory() as db:
            await db.execute(
                update(LegalAnswerCache)
                .where(LegalAnswerCache.id == cache_id)
                .values(
                    hit_count=LegalAnswerCache.hit_count + 1,
                    last_hit_at=func.now(),
                    updated_at=func.now(),
                )
            )
            await db.commit()

    async def invalidate(self, cache_id: uuid.UUID) -> None:
        async with SessionFactory() as db:
            await db.execute(
                update(LegalAnswerCache)
                .where(LegalAnswerCache.id == cache_id)
                .values(expires_at=func.now(), updated_at=func.now())
            )
            await db.commit()
