from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import unicodedata
from datetime import date, datetime
from typing import Any, Literal

from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.external_graphrag import (
    ExternalGraphRAGConfig,
    Neo4jGraphRAGStore,
    Neo4jPostgresGraphRAGStore,
    PostgresGraphRAGStore,
)
from app.legal_graphrag import GraphRAGStore
from app.services.ai import untrusted_data_block
from app.services.embeddings import (
    EmbeddingConfig,
    embedding_config_from_settings,
    parse_vertex_locations,
)

logger = logging.getLogger(__name__)


_WORD_RE = re.compile(r"[0-9A-Za-zÀ-ỹĐđ]+", re.UNICODE)
_COMPOUND_SPLIT_RE = re.compile(
    r"(?:[;?]\s*|,\s+(?=(?:khi|nếu|còn|đồng thời)\b)|"
    r"\s+(?:và|còn|đồng thời)\s+(?=(?:khi|nếu|tôi|bạn|công ty|"
    r"người lao động|người sử dụng lao động|cách|mức|thời|điều kiện|"
    r"bị|được|phải|ở đâu|biện pháp|quyền|nghĩa vụ)\b))",
    re.IGNORECASE,
)
_AGGREGATIVE_MARKERS = (
    "tong hop",
    "liet ke",
    "day du",
    "toan bo",
    "tat ca",
    "so sanh",
    "phan biet",
    "cac khoan",
    "nhung khoan",
    "cac nghia vu",
    "nhung nghia vu",
    "cac quyen",
    "nhung quyen",
    "cac buoc",
    "nhung truong hop",
    "cac che do",
    "cac hanh vi",
    "ho so rui ro",
)
_MULTI_ABSTRACT_MARKERS = (
    *_AGGREGATIVE_MARKERS,
    "phan tich",
    "danh gia",
    "he thong hoa",
    "tong quan",
    "quyen va nghia vu",
    "dieu kien va thu tuc",
    "ho so va thu tuc",
    "rui ro va giai phap",
    "uu diem va nhuoc diem",
    "nhieu van ban",
    "nhieu linh vuc",
)
_MULTI_HOP_PATTERNS = (
    re.compile(r"\bneu\b.+\bthi\b", re.IGNORECASE),
    re.compile(r"\b(?:sau khi|truoc khi|ke tu khi|tiep theo)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:dan den|keo theo|lam phat sinh|anh huong den|"
        r"moi quan he giua|phu thuoc vao)\b",
        re.IGNORECASE,
    ),
)
_LEGAL_REFERENCE_RE = re.compile(
    r"\b(?:dieu|khoan|diem)\s+\d+[a-z]?\b",
    re.IGNORECASE,
)
_QUERY_STOP_WORDS = {
    "ai",
    "bao",
    "ban",
    "bi",
    "cac",
    "cho",
    "co",
    "cua",
    "duoc",
    "gi",
    "hay",
    "hoi",
    "khong",
    "la",
    "lam",
    "loi",
    "mot",
    "nao",
    "neu",
    "nhieu",
    "nhu",
    "nhung",
    "nguoi",
    "phap",
    "quy",
    "so",
    "the",
    "theo",
    "thi",
    "toi",
    "trong",
    "va",
    "ve",
    "voi",
}
_SPECIFIC_DOMAIN_ANCHORS: tuple[tuple[str, ...], ...] = (
    (
        "giet nguoi",
        "giet",
        "sat hai",
        "bao che",
        "che giau toi pham",
        "toi pham",
        "hinh su",
        "tron na",
        "cuop",
        "trom cap",
    ),
    (
        "ly hon",
        "ket hon",
        "cap duong",
        "quyen nuoi con",
        "chia tai san chung",
        "hon nhan gia dinh",
    ),
)
_SHARED_TOPIC_TERMS = {
    "an toàn",
    "bảo hiểm",
    "giấy phép",
    "hợp đồng",
    "hưu",
    "kỷ luật",
    "lương",
    "nội quy",
    "thai sản",
    "thời giờ",
    "thuế",
    "tiền",
    "trợ cấp",
}
_LEGAL_QUERY_EXPANSIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("luong co ban", "luong vung", "muc luong vung"),
        (
            "tiền lương mức lương theo công việc mức lương tối thiểu vùng "
            "hiện hành mới nhất Điều 3 Điều 4 Điều 90 Điều 91"
        ),
    ),
    (
        ("lam le", "ngay le", "le tet"),
        "tiền lương làm thêm giờ ngày nghỉ lễ tết 300% Điều 98",
    ),
    (
        ("bao che",),
        "che giấu tội phạm không tố giác tội phạm trách nhiệm hình sự",
    ),
)


def _ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(
        "d" if character in {"Đ", "đ"} else character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    ).lower()


def _significant_terms(value: str) -> list[str]:
    return list(
        dict.fromkeys(
            token
            for token in _WORD_RE.findall(_ascii(value))
            if len(token) >= 3 and token not in _QUERY_STOP_WORDS
        )
    )


def _accented_significant_terms(value: str) -> list[str]:
    return list(
        dict.fromkeys(
            token.casefold()
            for token in _WORD_RE.findall(value)
            if len(_ascii(token)) >= 3
            and _ascii(token) not in _QUERY_STOP_WORDS
        )
    )


def _is_aggregative_query(query: str) -> bool:
    query_ascii = _ascii(query)
    return any(marker in query_ascii for marker in _AGGREGATIVE_MARKERS)


def _question_facets(query: str) -> list[str]:
    return [
        facet.strip(" ,.;:?")
        for facet in _COMPOUND_SPLIT_RE.split(query)
        if facet and len(_significant_terms(facet)) >= 1
    ]


RetrievalRoute = Literal["single_hop", "multi_hop", "multi_abstract"]


def classify_retrieval_route(query: str) -> RetrievalRoute:
    """Classify the original question without counting search expansions."""

    normalized = " ".join(str(query or "").split())
    if not normalized:
        return "single_hop"

    query_ascii = _ascii(normalized)
    if any(marker in query_ascii for marker in _MULTI_ABSTRACT_MARKERS):
        return "multi_abstract"

    facets = _question_facets(normalized)
    legal_references = {
        match.casefold() for match in _LEGAL_REFERENCE_RE.findall(query_ascii)
    }
    if (
        len(facets) >= 2
        or len(legal_references) >= 2
        or any(pattern.search(query_ascii) for pattern in _MULTI_HOP_PATTERNS)
    ):
        return "multi_hop"
    return "single_hop"


def plan_retrieval_queries(query: str) -> list[str]:
    """Create deterministic facet queries for compound legal questions.

    The original question is always retained.  Extra queries isolate each
    explicit issue so one lexically dominant clause cannot hide the other
    legal rule needed by a multi-hop answer.
    """

    normalized = " ".join(str(query or "").split())
    if not normalized:
        return []

    planned = [normalized]
    facets = _question_facets(normalized)
    if len(facets) >= 2:
        first_ascii = _ascii(facets[0])
        first_terms = [
            topic
            for topic in sorted(_SHARED_TOPIC_TERMS, key=len, reverse=True)
            if _ascii(topic) in first_ascii
        ][:2]
        shared_prefix = " ".join(first_terms)
        for index, facet in enumerate(facets):
            expanded = facet
            if index and shared_prefix:
                facet_terms = set(_significant_terms(facet))
                if not facet_terms.intersection(
                    _ascii(term) for term in first_terms
                ):
                    expanded = f"{shared_prefix} {facet}"
            if expanded.casefold() != normalized.casefold():
                planned.append(expanded)
    query_ascii = _ascii(normalized)
    matched_expansions = []
    for markers, expansion in _LEGAL_QUERY_EXPANSIONS:
        if any(marker in query_ascii for marker in markers):
            matched_expansions.append(expansion)
    if matched_expansions and len(facets) < 2:
        # One expanded search preserves the user's wording while avoiding a
        # second sequential vector + BM25 round trip for simple questions.
        planned[0] = " ".join([normalized, *matched_expansions])
    else:
        planned.extend(matched_expansions)
    return list(dict.fromkeys(planned))[:5]


def adaptive_retrieval_top_k(query: str, base_top_k: int) -> int:
    base = max(1, int(base_top_k))
    planned = plan_retrieval_queries(query)
    if _is_aggregative_query(query):
        return min(32, max(24, base * 2 + 4))
    if len(planned) > 1:
        return min(28, max(18, base + 8))
    return base


def build_answer_plan(query: str) -> dict[str, Any]:
    """Expose question coverage and actor focus to the synthesis prompt."""

    planned = plan_retrieval_queries(query)
    facets = _question_facets(" ".join(str(query or "").split()))
    if not facets and planned:
        facets = [planned[0]]
    query_ascii = _ascii(query)
    actor_patterns = (
        ("bạn tôi", r"\bban toi\b"),
        ("tôi", r"\btoi\b"),
        ("công ty", r"\bcong ty\b"),
        ("người lao động", r"\bnguoi lao dong\b"),
        ("người sử dụng lao động", r"\bnguoi su dung lao dong\b"),
    )
    actors = [
        label for label, pattern in actor_patterns
        if re.search(pattern, query_ascii)
    ]
    focus = ""
    for label in ("tôi", "người lao động", "công ty", "người sử dụng lao động"):
        label_ascii = _ascii(label)
        if re.search(
            rf"\b{re.escape(label_ascii)}\b.{{0,24}}\b"
            r"(?:bi|phai|duoc|co the|loi gi|toi gi|xu ly)\b",
            query_ascii,
        ):
            focus = label
            break
    return {
        "mode": classify_retrieval_route(query),
        "must_answer": facets,
        "actors": actors,
        "focus_actor": focus or (actors[-1] if actors else ""),
    }


def _rows_have_query_evidence(query: str, rows: list[dict[str, Any]]) -> bool:
    """Reject vector-only, out-of-domain matches with no lexical evidence."""

    if not rows:
        return False
    query_ascii = _ascii(query)
    evidence = _ascii(
        " ".join(
            f"{row.get('title', '')} {row.get('citation', '')} "
            f"{row.get('text', '')}"
            for row in rows[:24]
        )
    )
    criminal_fact_anchors = (
        "giet nguoi",
        "giet",
        "sat hai",
        "bao che",
    )
    if any(anchor in query_ascii for anchor in criminal_fact_anchors):
        document_labels = _ascii(
            " ".join(
                str(row.get("citation") or row.get("title") or "").split(">", 1)[0]
                for row in rows[:24]
            )
        )
        if (
            "bo luat hinh su" not in document_labels
            and "luat hinh su" not in document_labels
        ):
            return False
        return any(
            anchor in evidence
            for anchor in (
                "giet nguoi",
                "giet",
                "sat hai",
                "che giau toi pham",
                "khong to giac toi pham",
            )
        )
    for group in _SPECIFIC_DOMAIN_ANCHORS:
        if any(anchor in query_ascii for anchor in group):
            return any(anchor in evidence for anchor in group)
    anchors = _significant_terms(query)
    return not anchors or any(anchor in evidence for anchor in anchors)


_LEGAL_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_EXPLICIT_LEGAL_VERSION_RE = re.compile(
    r"(?:\b\d{1,4}/(?:19|20)\d{2}(?:/|-)|\bnam\s+(?:19|20)\d{2}\b)"
)


def _retrieved_legal_version(row: dict[str, Any]) -> tuple[str, str, int] | None:
    """Return a comparable (instrument family, locator, year) tuple.

    Corpus citations contain the instrument title and number in their first
    segment, followed by the article/clause path.  Removing only the numbered
    parenthetical lets us compare equivalent provisions across yearly
    replacements without treating unrelated instruments as versions.
    """

    citation = str(row.get("citation") or row.get("title") or "").strip()
    if not citation:
        return None
    label, separator, locator = citation.partition(">")
    years = [int(match) for match in _LEGAL_YEAR_RE.findall(label)]
    if not years:
        return None
    family = re.sub(
        r"\([^)]*(?:19|20)\d{2}[^)]*\)",
        " ",
        _ascii(label),
    )
    family = re.sub(r"[^a-z0-9]+", " ", family).strip()
    normalized_locator = re.sub(
        r"[^a-z0-9]+",
        " ",
        _ascii(locator if separator else ""),
    ).strip()
    if not family:
        return None
    return family, normalized_locator, max(years)


def _prefer_latest_retrieved_legal_versions(
    query: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop stale duplicates only when an equivalent newer provision exists.

    A query that explicitly names a legal version/year remains historical and
    keeps every retrieved version.  This is deliberately not a replacement
    for authoritative freshness metadata; it prevents contradictory versions
    of the same titled provision from entering one current/general answer.
    """

    if _EXPLICIT_LEGAL_VERSION_RE.search(_ascii(query)):
        return rows

    versions: dict[tuple[str, str], int] = {}
    parsed: list[tuple[dict[str, Any], tuple[str, str, int] | None]] = []
    for row in rows:
        version = _retrieved_legal_version(row)
        parsed.append((row, version))
        if version is None:
            continue
        family, locator, year = version
        key = (family, locator)
        versions[key] = max(versions.get(key, year), year)

    selected: list[dict[str, Any]] = []
    for row, version in parsed:
        if version is None:
            selected.append(row)
            continue
        family, locator, year = version
        if year < versions[(family, locator)]:
            continue
        reasons = [*row.get("reasons", []), "newest_retrieved_legal_version"]
        row["reasons"] = list(dict.fromkeys(str(item) for item in reasons))
        selected.append(row)
    return selected


def _merge_retrieval_rows(
    result_sets: list[list[dict[str, Any]]],
    limit: int,
    queries: list[str] | None = None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {}
    coverage: dict[str, set[int]] = {}
    for query_index, rows in enumerate(result_sets):
        query_weight = 1.15 if query_index == 0 else 1.0
        query_terms = _accented_significant_terms(
            queries[query_index]
            if queries and query_index < len(queries)
            else ""
        )
        for rank, raw_row in enumerate(rows, start=1):
            row = dict(raw_row)
            key = str(
                row.get("chunk_id")
                or row.get("node_id")
                or f"{row.get('doc_id', '')}:{row.get('citation', '')}:{row.get('text', '')[:120]}"
            )
            if key not in merged:
                merged[key] = row
                coverage[key] = set()
                scores[key] = 0.0
            coverage[key].add(query_index)
            row_tokens = set(
                _WORD_RE.findall(
                    f"{row.get('title', '')} {row.get('citation', '')} "
                    f"{row.get('text', '')[:1200]}".casefold()
                )
            )
            lexical_coverage = (
                sum(term in row_tokens for term in query_terms)
                / min(len(query_terms), 10)
                if query_terms
                else 0.0
            )
            scores[key] += (
                query_weight
                / (8.0 + rank)
                * (0.5 + lexical_coverage)
            )
            reasons = [
                *merged[key].get("reasons", []),
                *row.get("reasons", []),
                f"query_facet:{query_index}",
            ]
            merged[key]["reasons"] = list(dict.fromkeys(str(item) for item in reasons))

    for key, row in merged.items():
        scores[key] += max(0, len(coverage[key]) - 1) * 0.035
        row["score"] = round(scores[key], 4)

    ranked = sorted(
        merged.values(),
        key=lambda row: (
            -float(row.get("score") or 0),
            str(row.get("chunk_id") or row.get("citation") or ""),
        ),
    )
    ranked = _prefer_latest_retrieved_legal_versions(
        queries[0] if queries else "",
        ranked,
    )
    selected: list[dict[str, Any]] = []
    per_document: dict[str, int] = {}
    deferred: list[dict[str, Any]] = []
    document_cap = max(5, int(limit * 0.45))
    for row in ranked:
        document = str(row.get("doc_id") or row.get("citation") or "")
        if per_document.get(document, 0) >= document_cap:
            deferred.append(row)
            continue
        selected.append(row)
        per_document[document] = per_document.get(document, 0) + 1
        if len(selected) >= limit:
            return selected
    selected.extend(deferred[: max(0, limit - len(selected))])
    return selected[:limit]


def _embedding_config(settings: Settings) -> EmbeddingConfig:
    return embedding_config_from_settings(settings)


def _external_config(settings: Settings) -> ExternalGraphRAGConfig:
    return ExternalGraphRAGConfig(
        neo4j_uri=settings.neo4j_uri,
        neo4j_user=settings.neo4j_user,
        neo4j_password=settings.neo4j_password,
        neo4j_database=settings.neo4j_database,
        database_url=settings.database_url,
        postgres_vector_size=settings.postgres_vector_size,
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        embedding_project_id=settings.gemini_project_id,
        embedding_location=settings.embedding_location,
        embedding_credentials_path=settings.gemini_credentials_path,
        embedding_use_adc=settings.gemini_use_adc,
        embedding_api_key=settings.gemini_api_key,
        embedding_max_concurrency=settings.embedding_max_concurrency,
        embedding_batch_size=settings.embedding_batch_size,
        embedding_max_items_per_minute=(
            settings.embedding_max_items_per_minute
        ),
        embedding_timeout_seconds=settings.embedding_timeout_seconds,
        embedding_max_retries=settings.embedding_max_retries,
        embedding_auto_truncate=settings.embedding_auto_truncate,
        embedding_data_policy=settings.gemini_data_policy,
        embedding_vertex_locations=parse_vertex_locations(
            settings.embedding_vertex_locations
        ),
        embedding_vertex_requests_per_minute=(
            settings.embedding_vertex_requests_per_minute
        ),
        embedding_vertex_max_queue_wait_seconds=(
            settings.embedding_vertex_max_queue_wait_seconds
        ),
        retrieval_postgres_pool_size=settings.retrieval_postgres_pool_size,
        hybrid_vector_weight=settings.hybrid_vector_weight,
        hybrid_bm25_weight=settings.hybrid_bm25_weight,
        hybrid_rrf_k=settings.hybrid_rrf_k,
        bm25_k1=settings.bm25_k1,
        bm25_b=settings.bm25_b,
    )


class RetrievalService:
    """One store per worker; blocking vendor SDKs are isolated from the event loop."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._store: Any = None
        self._graph_store: Any = None
        self._lock = asyncio.Lock()

    async def _get_store(
        self,
        route: RetrievalRoute = "single_hop",
    ) -> Any:
        backend = getattr(self.settings, "retriever_backend", "rag")
        use_graph = (
            route in {"multi_hop", "multi_abstract"}
            and backend in {"hybrid_rag", "graphrag"}
        )
        attribute = "_graph_store" if use_graph else "_store"
        existing = getattr(self, attribute)
        if existing is not None:
            return existing
        async with self._lock:
            existing = getattr(self, attribute)
            if existing is not None:
                return existing
            config = _external_config(self.settings)
            try:
                if use_graph and backend == "hybrid_rag":
                    store = await run_in_threadpool(
                        Neo4jPostgresGraphRAGStore,
                        config,
                    )
                elif use_graph and backend == "graphrag":
                    store = await run_in_threadpool(
                        Neo4jGraphRAGStore,
                        config,
                    )
                else:
                    store = await run_in_threadpool(
                        PostgresGraphRAGStore,
                        config,
                    )
            except Exception as exc:
                logger.warning(
                    "Retriever %s route=%s failed to initialize: %s. "
                    "Falling back to PostgresGraphRAGStore.",
                    backend,
                    route,
                    exc,
                )
                try:
                    store = await run_in_threadpool(
                        PostgresGraphRAGStore,
                        config,
                    )
                except Exception as fallback_exc:
                    logger.error(
                        "PostgresGraphRAGStore fallback failed: %s",
                        fallback_exc,
                    )
                    raise
            setattr(self, attribute, store)
        return store

    async def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        retrieval_started = time.perf_counter()
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
        try:
            route = classify_retrieval_route(query)
            store_started = time.perf_counter()
            store = await self._get_store(route)
            store_init_ms = round(
                (time.perf_counter() - store_started) * 1000
            )
            logger.info(
                "Retrieval route=%s backend=%s",
                route,
                getattr(self.settings, "retriever_backend", "rag"),
            )
            base_top_k = top_k or self.settings.retrieval_top_k
            planned_queries = plan_retrieval_queries(query)
            result_limit = adaptive_retrieval_top_k(query, base_top_k)
            if len(planned_queries) == 1:
                # Keep a wider local candidate window before version
                # deduplication. Equivalent older provisions can otherwise
                # occupy the entire top-k and hide their current replacement
                # (for example NĐ 38/2022 ahead of NĐ 293/2025).
                per_query_limit = max(base_top_k, 24)
            else:
                per_query_limit = max(
                    base_top_k,
                    min(
                        18,
                        max(
                            10,
                            (
                                result_limit
                                + len(planned_queries)
                                - 1
                            )
                            // len(planned_queries),
                        ),
                    ),
                )
            result_sets = []
            store_query_ms = 0
            for planned_query in planned_queries:
                store_query_started = time.perf_counter()
                result_sets.append(
                    await run_in_threadpool(
                        store.retrieve,
                        planned_query,
                        per_query_limit,
                    )
                )
                store_query_ms += round(
                    (time.perf_counter() - store_query_started) * 1000
                )
            merge_started = time.perf_counter()
            rows = _merge_retrieval_rows(
                result_sets,
                result_limit,
                planned_queries,
            )
            merge_filter_ms = round(
                (time.perf_counter() - merge_started) * 1000
            )
            if not _rows_have_query_evidence(query, rows):
                logger.info(
                    "Retrieval service completed query_sha256=%s route=%s "
                    "planned_queries=%d store_init_ms=%d store_query_ms=%d "
                    "merge_filter_ms=%d final_sources=0 total_ms=%d",
                    query_hash,
                    route,
                    len(planned_queries),
                    store_init_ms,
                    store_query_ms,
                    merge_filter_ms,
                    round((time.perf_counter() - retrieval_started) * 1000),
                )
                return []
            serialized = [serialize_source(row) for row in rows]
            for index, source in enumerate(serialized, start=1):
                source["source_id"] = f"S{index}"
            logger.info(
                "Retrieval service completed query_sha256=%s route=%s "
                "planned_queries=%d store_init_ms=%d store_query_ms=%d "
                "merge_filter_ms=%d final_sources=%d total_ms=%d",
                query_hash,
                route,
                len(planned_queries),
                store_init_ms,
                store_query_ms,
                merge_filter_ms,
                len(serialized),
                round((time.perf_counter() - retrieval_started) * 1000),
            )
            return serialized
        except Exception as exc:
            logger.warning("Retrieve operation failed: %s", exc)
            return []

    async def stats(self) -> dict[str, Any]:
        backend = getattr(self.settings, "retriever_backend", "rag")
        route: RetrievalRoute = (
            "multi_hop"
            if backend in {"hybrid_rag", "graphrag"}
            else "single_hop"
        )
        store = await self._get_store(route)
        return await run_in_threadpool(store.stats)

    async def close(self) -> None:
        closed: set[int] = set()
        for store in (self._store, self._graph_store):
            if (
                store is not None
                and id(store) not in closed
                and hasattr(store, "close")
            ):
                await run_in_threadpool(store.close)
                closed.add(id(store))

    def invalidate(self) -> None:
        self._store = None
        self._graph_store = None


def serialize_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": str(source.get("source_id", "")),
        "score": round(float(source.get("score", 0) or 0), 4),
        "chunk_type": str(source.get("chunk_type", "")),
        "citation": str(source.get("citation") or source.get("title") or "Nguồn pháp lý")[:500],
        "title": str(source.get("title") or "")[:500],
        "text": str(source.get("text") or "")[:5000],
        "reasons": [str(item) for item in source.get("reasons", [])],
        "doc_id": str(source.get("doc_id")) if source.get("doc_id") else None,
        "node_id": str(source.get("node_id")) if source.get("node_id") else None,
        "law_code": str(source.get("law_code")) if source.get("law_code") else None,
        "source_url": source.get("source_url"),
        "law_status": source.get("law_status"),
        "law_version": source.get("law_version"),
        "effective_date": (
            _display_legal_date(source.get("effective_date")) or None
        ),
        "law_checked_at": (
            _display_legal_date(source.get("law_checked_at")) or None
        ),
    }


def select_context_sources(
    sources: list[dict[str, Any]],
    max_chars: int = 48000,
) -> list[dict[str, Any]]:
    """Return exactly the sources that fit in the model context budget."""

    selected: list[dict[str, Any]] = []
    size = 0
    for source in sources:
        row = {
            "source_id": str(source.get("source_id") or ""),
            "citation": str(source.get("citation") or ""),
            "text": str(source.get("text") or ""),
        }
        row_size = sum(len(value) for value in row.values())
        if size + row_size > max_chars:
            break
        selected.append(source)
        size += row_size
    return selected


def compact_context_sources(
    sources: list[dict[str, Any]],
    query: str,
    *,
    max_chars: int = 14000,
    per_source_chars: int = 1800,
) -> list[dict[str, Any]]:
    """Copy sources into a query-focused prompt budget without changing UI data.

    Retrieval chunks can be several thousand characters long. Sending six full
    chunks makes a simple answer slower even when only one short provision in
    each chunk is relevant. Keep every selected source ID/citation, but trim
    long text to the overlapping window with the strongest query-term coverage.
    The original source objects remain untouched for validation and display.
    """

    if max_chars <= 0 or per_source_chars <= 0:
        return []
    terms = _accented_significant_terms(query)
    compacted: list[dict[str, Any]] = []
    used_chars = 0

    for source in sources:
        row = dict(source)
        source_id = str(row.get("source_id") or "")
        citation = str(row.get("citation") or "")
        text = str(row.get("text") or "")
        metadata_chars = len(source_id) + len(citation)
        remaining = max_chars - used_chars - metadata_chars
        if remaining <= 0:
            break
        text_budget = min(per_source_chars, remaining)

        if len(text) > text_budget:
            step = max(text_budget // 2, 1)
            starts = range(0, max(len(text) - text_budget + 1, 1), step)

            def window_score(start: int) -> tuple[int, int]:
                window = text[start : start + text_budget].casefold()
                return (
                    sum(term in window for term in terms),
                    -start,
                )

            best_start = max(starts, key=window_score, default=0)
            if best_start + text_budget < len(text):
                tail_start = len(text) - text_budget
                if window_score(tail_start) > window_score(best_start):
                    best_start = tail_start
            excerpt = text[best_start : best_start + text_budget].strip()
            if best_start > 0:
                excerpt = f"…{excerpt.lstrip()}"
            if best_start + text_budget < len(text):
                excerpt = f"{excerpt.rstrip()}…"
            row["text"] = excerpt

        row_chars = metadata_chars + len(str(row.get("text") or ""))
        if row_chars > max_chars - used_chars:
            break
        compacted.append(row)
        used_chars += row_chars

    return compacted


def format_source_locator(source: dict[str, Any]) -> str:
    citation = " ".join(str(source.get("citation") or "").split())
    segments = [segment.strip() for segment in citation.split(">") if segment.strip()]
    document = segments[0] if segments else citation or "Nguồn pháp lý"
    article = next(
        (
            match.group(1)
            for segment in segments
            if (match := re.search(r"\bĐiều\s+(\d+[A-Za-z]?)\b", segment, re.IGNORECASE))
        ),
        "",
    )
    clause = next(
        (
            match.group(1)
            for segment in segments
            if (match := re.search(r"\bKhoản\s+(\d+[A-Za-z]?)\b", segment, re.IGNORECASE))
        ),
        "",
    )
    point = next(
        (
            match.group(1)
            for segment in segments
            if (match := re.search(r"\bĐiểm\s+([A-Za-zĐđ])\b", segment, re.IGNORECASE))
        ),
        "",
    )
    code_match = re.search(
        r"\b(?:\d{1,4}/\d{4}/[A-ZĐ][A-ZĐ0-9-]{1,30}|"
        r"\d{1,4}/VBHN-[A-ZĐ0-9-]{1,30})\b",
        document,
        re.IGNORECASE,
    )
    code = code_match.group(0).upper() if code_match else ""
    if code:
        document_name = re.sub(
            rf"\s*\({re.escape(code)}\)\s*$",
            "",
            document,
            flags=re.IGNORECASE,
        ).strip()
        document = f"{document_name} số {code}"

    parts = []
    if article:
        parts.append(f"Điều {article}")
    if clause:
        parts.append(f"khoản {clause}")
    if point:
        parts.append(f"điểm {point.lower()}")
    parts.append(document)

    issuer = ""
    if re.search(r"/UBTVQH\d*$", code):
        issuer = "Ủy ban Thường vụ Quốc hội"
    elif re.search(r"/QH\d+(?:-\d+)?$", code):
        issuer = "Quốc hội"
    elif code.endswith("NĐ-CP"):
        issuer = "Chính phủ"
    elif code.endswith("TT-BTC"):
        issuer = "Bộ Tài chính"
    elif code.endswith("TT-BNV"):
        issuer = "Bộ Nội vụ"
    elif code.endswith("TT-BLĐTBXH"):
        issuer = "Bộ Lao động - Thương binh và Xã hội"
    if issuer:
        parts.append(f"do {issuer} ban hành")
    return ", ".join(part for part in parts if part)


def _display_legal_date(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            return ""
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw)
            if not match:
                return ""
            return (
                f"{match.group(1).zfill(2)}/"
                f"{match.group(2).zfill(2)}/{match.group(3)}"
            )
    return parsed.strftime("%d/%m/%Y")


def format_source_opening(source: dict[str, Any]) -> str:
    """Build the exact safe opening requested from verified source metadata."""

    opening = f"Theo {format_source_locator(source)}"
    effective_date = _display_legal_date(source.get("effective_date"))
    checked_at = _display_legal_date(source.get("law_checked_at"))
    status = str(source.get("law_status") or "").strip().upper()
    if effective_date:
        opening += f", có hiệu lực từ ngày {effective_date}"
    elif checked_at and status in {
        "IN_FORCE",
        "PARTIALLY_IN_FORCE",
        "AMENDED",
    }:
        opening += (
            f", đang được xác nhận còn hiệu lực tại ngày {checked_at}"
        )
    return opening


def append_detailed_citations(
    answer: str,
    sources: list[dict[str, Any]],
) -> str:
    """Render deterministic, human-readable legal locators for cited IDs."""

    if "\nCăn cứ được trích dẫn:\n" in answer:
        return answer
    source_by_id = {
        str(source.get("source_id") or "").upper(): source for source in sources
    }
    referenced = list(
        dict.fromkeys(
            match.upper()
            for match in re.findall(r"\[([A-Z]\d+)\]", answer, re.IGNORECASE)
            if match.upper() in source_by_id
        )
    )
    if not referenced:
        return answer
    details = [
        f"- {format_source_opening(source_by_id[source_id])} [{source_id}]."
        for source_id in referenced
    ]
    return f"{answer.rstrip()}\n\nCăn cứ được trích dẫn:\n" + "\n".join(details)


def build_context(sources: list[dict[str, Any]], max_chars: int = 48000) -> str:
    selected = [
        {
            "source_id": str(source["source_id"]),
            "citation": str(source["citation"]),
            "citation_format": (
                f"{format_source_opening(source)} "
                f"[{str(source['source_id'])}]"
            ),
            "effective_date": (
                _display_legal_date(source.get("effective_date")) or None
            ),
            "law_status": source.get("law_status"),
            "law_checked_at": (
                _display_legal_date(source.get("law_checked_at")) or None
            ),
            "text": str(source["text"]),
        }
        for source in select_context_sources(sources, max_chars=max_chars)
    ]
    return untrusted_data_block("LEGAL_SOURCES", selected)
