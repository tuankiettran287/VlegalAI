from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import uuid
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.config import Settings
from app.core.security import decrypt_text, encrypt_text
from app.db import SessionFactory
from app.models import LegalAnswerCache
from app.services.ai import redact_sensitive_text
from app.services.embeddings import (
    VertexAIEmbeddingService,
    embedding_config_from_settings,
    get_embedding_service,
)


LEGAL_ANSWER_PROMPT_VERSION = "legal-answer-v6-concise-public-cache"
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
    r"quyền|được phép|hiệu lực|hợp đồng|chấm dứt|lao động"
    r")\b",
    re.IGNORECASE,
)
_PERSON_TITLE_RE = re.compile(
    r"\b(?:ông|bà|anh|chị|ông/bà)\s+"
    r"[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠ-Ỹ][^\W\d_]+"
    r"(?:\s+[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠƯẠ-Ỹ][^\W\d_]+){1,4}\b",
)
_PUBLIC_TITLE_FIRST_WORDS = {
    "bộ",
    "chính",
    "điều",
    "luật",
    "nghị",
    "nhà",
    "người",
    "pháp",
    "quy",
    "theo",
    "thông",
    "thuế",
    "việt",
}
_PUBLIC_ACRONYMS = {
    "BHXH",
    "BLĐTBXH",
    "BTC",
    "CP",
    "GTGT",
    "NĐ",
    "QH",
    "TNCN",
    "TNDN",
    "TT",
    "UBTVQH",
    "VAT",
    "VND",
}


def _contains_likely_private_entity(query: str) -> bool:
    """Conservatively exclude named people/organizations from answer caching."""

    # Generic actor words such as "doanh nghiệp" and "người lao động" are
    # common in public legal questions. Named organizations are already
    # rejected by redact_sensitive_text() above and by the proper-name scan
    # below, so treating every generic organization noun as private disabled
    # the cache for a large share of ordinary labour-law questions.
    if _PERSON_TITLE_RE.search(query):
        return True

    words = re.findall(r"[^\W\d_]+", query, flags=re.UNICODE)
    proper_run = 0
    for index, word in enumerate(words):
        is_title_case = len(word) > 1 and word[0].isupper() and word[1:].islower()
        if is_title_case:
            if (
                proper_run == 0
                and index == 0
                and word.casefold() in _PUBLIC_TITLE_FIRST_WORDS
            ):
                proper_run = 0
                continue
            proper_run += 1
            if proper_run >= 2:
                return True
        else:
            proper_run = 0

        if (
            len(word) >= 2
            and word.isupper()
            and word not in _PUBLIC_ACRONYMS
        ):
            return True
    return False


def normalize_public_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", query).casefold()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return re.sub(r"[\s?!.,;:]+$", "", normalized)


def is_public_cache_candidate(query: str, *, max_chars: int = 1500) -> bool:
    normalized = normalize_public_query(query)
    _, sensitive_count = redact_sensitive_text(query)
    return (
        20 <= len(normalized) <= max_chars
        and bool(_PUBLIC_LEGAL_RE.search(normalized))
        and sensitive_count == 0
        and not _PRIVATE_CONTEXT_RE.search(normalized)
        and not _DIRECT_IDENTIFIER_RE.search(normalized)
        and not _contains_likely_private_entity(query)
    )


def legal_fingerprint(
    sources: list[dict[str, Any]],
    verification: dict[str, Any],
) -> str:
    source_identity = sorted(
        {
            (
                str(source.get("source_id") or ""),
                str(source.get("doc_id") or ""),
                str(source.get("citation") or ""),
                str(source.get("source_url") or ""),
                str(source.get("law_status") or ""),
                str(source.get("law_version") or ""),
                hashlib.sha256(
                    str(source.get("text") or "").encode("utf-8")
                ).hexdigest(),
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
    scope_hash: str
    query_hash: str
    normalized_query: str
    embedding: list[float] | None
    hit: CachedLegalAnswer | None


class SemanticAnswerCacheService:
    """Scoped cache restricted to context-free public legal questions."""

    def __init__(
        self,
        settings: Settings,
        embeddings: VertexAIEmbeddingService | None = None,
    ) -> None:
        self.settings = settings
        self.embedding_config = embedding_config_from_settings(settings)
        self.embeddings = embeddings or get_embedding_service(
            self.embedding_config
        )

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

    async def lookup(
        self,
        query: str,
        *,
        scope: str,
        allow_semantic: bool = True,
    ) -> CacheLookup:
        if not scope.strip():
            raise ValueError("Semantic answer cache scope must not be blank.")
        scope_hash = hashlib.sha256(scope.encode("utf-8")).hexdigest()
        normalized_query = normalize_public_query(query)
        query_hash = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        active = (
            LegalAnswerCache.expires_at > now,
            LegalAnswerCache.model_name == self.settings.gemini_model,
            LegalAnswerCache.prompt_version == LEGAL_ANSWER_PROMPT_VERSION,
            LegalAnswerCache.embedding_model == self.embedding_config.model,
            LegalAnswerCache.embedding_revision
            == self.embedding_config.model_revision,
        )
        async with SessionFactory() as db:
            exact = await db.scalar(
                select(LegalAnswerCache).where(
                    LegalAnswerCache.cache_scope_hash == scope_hash,
                    LegalAnswerCache.query_hash == query_hash,
                    *active,
                )
            )
            if exact:
                return CacheLookup(
                    scope_hash=scope_hash,
                    query_hash=query_hash,
                    normalized_query=normalized_query,
                    embedding=None,
                    hit=self._cached_answer(exact, 1.0, exact_match=True),
                )

        if not allow_semantic:
            return CacheLookup(
                scope_hash=scope_hash,
                query_hash=query_hash,
                normalized_query=normalized_query,
                embedding=None,
                hit=None,
            )

        try:
            embedding = await run_in_threadpool(
                self.embeddings.embed_similarity,
                normalized_query,
            )
        except Exception as exc:
            logger.warning("Vertex AI embedding unavailable for semantic cache: %s", exc)
            return CacheLookup(
                scope_hash=scope_hash,
                query_hash=query_hash,
                normalized_query=normalized_query,
                embedding=None,
                hit=None,
            )
        distance = LegalAnswerCache.query_embedding.cosine_distance(embedding)
        async with SessionFactory() as db:
            result = await db.execute(
                select(LegalAnswerCache, distance.label("distance"))
                .where(
                    LegalAnswerCache.cache_scope_hash == scope_hash,
                    *active,
                )
                .order_by(distance)
                .limit(1)
            )
            match = result.first()
        hit = None
        if match:
            similarity = 1.0 - float(match[1])
            if similarity >= self.settings.semantic_answer_cache_similarity:
                hit = self._cached_answer(
                    match[0],
                    similarity,
                    exact_match=False,
                )
        return CacheLookup(
            scope_hash=scope_hash,
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
        *,
        embed_missing: bool = True,
    ) -> None:
        embedding = lookup.embedding
        if embedding is None:
            if embed_missing:
                embedding = await run_in_threadpool(
                    self.embeddings.embed_similarity,
                    lookup.normalized_query,
                )
            else:
                # A zero vector is intentionally not indexed by pgvector's
                # cosine HNSW index. The row remains immediately reusable by
                # its exact query hash without spending another scarce Vertex
                # embedding request or competing with the next chat query.
                embedding = [0.0] * self.embedding_config.dimensions
        now = datetime.now(UTC)
        values = {
            "id": uuid.uuid4(),
            "cache_scope_hash": lookup.scope_hash,
            "query_hash": lookup.query_hash,
            "query_ciphertext": encrypt_text(lookup.normalized_query, self.settings),
            "answer_ciphertext": encrypt_text(answer, self.settings),
            "answer_hash": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            "query_embedding": embedding,
            "sources": sources,
            "verification": verification,
            "law_fingerprint": legal_fingerprint(sources, verification),
            "model_name": self.settings.gemini_model,
            "prompt_version": LEGAL_ANSWER_PROMPT_VERSION,
            "embedding_model": self.embedding_config.model,
            "embedding_revision": self.embedding_config.model_revision,
            "expires_at": now + timedelta(hours=self.settings.semantic_answer_cache_ttl_hours),
            "hit_count": 0,
        }
        statement = insert(LegalAnswerCache).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[
                LegalAnswerCache.cache_scope_hash,
                LegalAnswerCache.query_hash,
            ],
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
                "embedding_model": statement.excluded.embedding_model,
                "embedding_revision": statement.excluded.embedding_revision,
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
