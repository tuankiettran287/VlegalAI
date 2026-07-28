from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import external_graphrag as graphrag_module
from app.external_graphrag import (
    CURRENT_LAW_STATUSES,
    Neo4jGraphRAGStore,
    Neo4jPostgresGraphRAGStore,
    PostgresGraphRAGStore,
    UNVERIFIED_LAW_STATUS,
    bm25_score,
    bootstrap_provenance,
    postgres_current_chunk_predicate,
    postgres_latest_chunk_predicate,
    postgres_lexical_terms,
    postgres_or_tsquery,
    reciprocal_rank_fusion,
    validate_postgres_embeddings,
)
from app.services.retrieval import serialize_source


def _row(chunk_id: str, text: str = "nghia vu thue") -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": "doc",
        "node_id": chunk_id,
        "chunk_type": "semantic",
        "title": "",
        "path_label": "",
        "citation": "",
        "text": text,
        "token_count": 3,
        "ordinal": 0,
        "source_url": None,
    }


def test_serialized_retrieval_source_preserves_law_code() -> None:
    serialized = serialize_source(
        {
            **_row("labor-code"),
            "law_code": "45/2019/QH14",
            "citation": "Bộ luật Lao động > Điều 98",
        }
    )

    assert serialized["law_code"] == "45/2019/QH14"


def test_bootstrap_provenance_quarantines_unknown_documents() -> None:
    metadata = {
        "verified-doc": {
            "law_code": "45/2019/QH14",
            "source_url": "https://vanban.chinhphu.vn/example",
            "law_status": "IN_FORCE",
            "law_version": 2,
            "provenance_verified": True,
        }
    }

    assert bootstrap_provenance(metadata, "verified-doc") == metadata["verified-doc"]
    unknown = bootstrap_provenance(metadata, "legacy-doc")
    assert unknown["law_status"] == UNVERIFIED_LAW_STATUS
    assert unknown["law_version"] == 1
    assert unknown["source_url"] is None
    assert unknown["provenance_verified"] is False


def test_postgres_lexical_terms_preserve_vietnamese_and_remove_stop_words() -> None:
    terms = postgres_lexical_terms("Theo Điều 36, người sử dụng lao động được chấm dứt hợp đồng")

    assert "theo" not in terms
    assert "được" not in terms
    assert "điều" in terms
    assert "36" in terms
    assert "người" in terms
    assert "'người'" in postgres_or_tsquery(terms)


def test_bm25_rewards_term_frequency_and_normalizes_document_length() -> None:
    terms = ["thuế", "phạt"]
    document_frequencies = {"thuế": 10, "phạt": 2}
    short = _row("short", "thuế phạt phạt")
    long = {**_row("long", "thuế phạt phạt"), "token_count": 300}

    short_score = bm25_score(short, terms, document_frequencies, 1000, 50)
    long_score = bm25_score(long, terms, document_frequencies, 1000, 50)

    assert short_score > long_score > 0


def test_reciprocal_rank_fusion_rewards_candidates_found_by_both_routes() -> None:
    scores = reciprocal_rank_fusion(
        [(["vector-only", "both"], 0.55), (["both", "bm25-only"], 0.45)],
        rank_constant=60,
    )

    assert scores["both"] > scores["vector-only"]
    assert scores["both"] > scores["bm25-only"]


def test_postgres_store_returns_fused_reasons() -> None:
    store = object.__new__(PostgresGraphRAGStore)
    store.config = SimpleNamespace(
        hybrid_vector_weight=0.55,
        hybrid_bm25_weight=0.45,
        hybrid_rrf_k=60,
    )
    store._vector_candidates = lambda query, limit: [_row("vector-only"), _row("both")]
    store._bm25_candidates = lambda query, limit: [_row("both"), _row("bm25-only")]

    rows = store.retrieve("nghia vu thue", top_k=3)

    assert rows[0]["chunk_id"] == "both"
    assert rows[0]["reasons"] == ["postgres_vector_cosine", "postgres_bm25"]
    assert {row["chunk_id"] for row in rows} == {"vector-only", "both", "bm25-only"}


def test_neo4j_hybrid_expands_postgres_rag_seeds() -> None:
    store = object.__new__(Neo4jPostgresGraphRAGStore)
    seed = {
        **_row("seed"),
        "node_id": "seed-node",
        "score": 2.0,
        "reasons": ["postgres_vector_cosine", "postgres_bm25"],
    }
    related = {**_row("related"), "node_id": "related-node", "chunk_type": "clause"}
    store._postgres_candidates = lambda query, limit: [seed]
    store._expand_node_scores = lambda node_scores: {
        "seed-node": node_scores["seed-node"],
        "related-node": 1.7,
    }
    store._chunks_for_nodes = lambda node_ids: [related]

    rows = store.retrieve("nghia vu thue", top_k=3)

    assert rows[0]["chunk_id"] == "seed"
    assert rows[0]["reasons"] == ["postgres_vector_cosine", "postgres_bm25"]
    assert rows[1]["chunk_id"] == "related"
    assert rows[1]["reasons"] == ["neo4j_graph"]


def test_neo4j_hybrid_falls_back_to_postgres_when_graph_is_unavailable() -> None:
    store = object.__new__(Neo4jPostgresGraphRAGStore)
    seed = {
        **_row("seed"),
        "node_id": "seed-node",
        "score": 2.0,
        "reasons": ["postgres_vector_cosine", "postgres_bm25"],
    }
    store._postgres_candidates = lambda query, limit: [seed]

    def unavailable(_: dict[str, float]) -> dict[str, float]:
        raise RuntimeError("Neo4j unavailable")

    store._expand_node_scores = unavailable

    rows = store.retrieve("nghia vu thue", top_k=3)

    assert [row["chunk_id"] for row in rows] == ["seed"]
    assert rows[0]["source_id"] == "S1"
    assert rows[0]["reasons"] == ["postgres_vector_cosine", "postgres_bm25"]


def test_neo4j_hybrid_can_skip_graph_expansion_for_single_hop_chat() -> None:
    store = object.__new__(Neo4jPostgresGraphRAGStore)
    seed = {
        **_row("seed"),
        "node_id": "seed-node",
        "score": 2.0,
        "reasons": ["postgres_vector_cosine", "postgres_bm25"],
    }
    recorded_limits: list[int] = []

    def retrieve(_: str, limit: int) -> list[dict]:
        recorded_limits.append(limit)
        return [seed]

    store.rag = SimpleNamespace(retrieve=retrieve)
    store._expand_node_scores = lambda _: (_ for _ in ()).throw(
        AssertionError("Graph expansion must not run")
    )

    rows = store.retrieve("nghia vu thue", top_k=3, expand_graph=False)

    assert [row["chunk_id"] for row in rows] == ["seed"]
    assert rows[0]["source_id"] == "S1"
    assert recorded_limits == [3]


def test_neo4j_hybrid_defers_connectivity_check_until_graph_use(
    monkeypatch,
) -> None:
    class _LazyDriver:
        def verify_connectivity(self) -> None:
            raise AssertionError("Hybrid store must not connect eagerly")

    driver = _LazyDriver()
    rag = SimpleNamespace(connection=object())
    monkeypatch.setattr(graphrag_module, "PostgresGraphRAGStore", lambda _: rag)
    monkeypatch.setattr(graphrag_module, "neo4j_driver", lambda _: driver)

    store = Neo4jPostgresGraphRAGStore(SimpleNamespace(ready=True))

    assert store.rag is rag
    assert store.postgres is rag.connection
    assert store.driver is driver


class _RecordingCursor:
    def __init__(
        self,
        *,
        fetchall_results: list[list[dict]] | None = None,
        fetchone_results: list[dict] | None = None,
    ) -> None:
        self.queries: list[tuple[str, object]] = []
        self.fetchall_results = list(fetchall_results or [])
        self.fetchone_results = list(fetchone_results or [])

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, query: str, parameters: object = None) -> None:
        self.queries.append((query, parameters))

    def fetchall(self) -> list[dict]:
        return self.fetchall_results.pop(0) if self.fetchall_results else []

    def fetchone(self) -> dict | None:
        return self.fetchone_results.pop(0) if self.fetchone_results else None


class _RecordingConnection:
    def __init__(self, cursor: _RecordingCursor) -> None:
        self.recording_cursor = cursor

    def cursor(self) -> _RecordingCursor:
        return self.recording_cursor


class _GraphResult:
    def __init__(self, rows: list[dict] | None = None) -> None:
        self.rows = rows or []

    def data(self) -> list[dict]:
        return self.rows


class _GraphSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __enter__(self) -> "_GraphSession":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def run(self, query: str, **parameters: object) -> _GraphResult:
        self.calls.append((query, parameters))
        return _GraphResult()


class _GraphDriver:
    def __init__(self) -> None:
        self.recording_session = _GraphSession()

    def session(self, **_: object) -> _GraphSession:
        return self.recording_session


def test_postgres_embedding_validation_rejects_mixed_vector_spaces() -> None:
    cursor = _RecordingCursor(
        fetchall_results=[
            [
                {
                    "embedding_model": "gemini-embedding-001",
                    "embedding_revision": "vertex-ai-v1:redact",
                    "dimensions": 1024,
                },
                {
                    "embedding_model": "BAAI/bge-m3",
                    "embedding_revision": "main",
                    "dimensions": 1024,
                },
            ]
        ]
    )
    config = SimpleNamespace(
        embedding_model="gemini-embedding-001",
        postgres_vector_size=1024,
        embedding_config=SimpleNamespace(
            model_revision="vertex-ai-v1:redact"
        ),
    )

    with pytest.raises(RuntimeError, match="re-embed"):
        validate_postgres_embeddings(_RecordingConnection(cursor), config)


def test_current_postgres_predicate_requires_current_status_and_latest_version() -> None:
    predicate = postgres_current_chunk_predicate("candidate")

    assert all(status in predicate for status in CURRENT_LAW_STATUSES)
    assert "candidate.law_status IN" in predicate
    assert "candidate.law_code IS NOT NULL" in predicate
    assert "regexp_replace" in predicate
    assert "graphrag_law_version AS latest_law" in predicate
    assert "latest_law.latest_version = candidate.law_version" in predicate


def test_latest_postgres_predicate_accepts_indexed_statuses_and_latest_version() -> None:
    predicate = postgres_latest_chunk_predicate("candidate")

    assert "candidate.law_status IN" not in predicate
    assert "candidate.law_code IS NOT NULL" in predicate
    assert "regexp_replace" in predicate
    assert "graphrag_law_version AS latest_law" in predicate
    assert "latest_law.latest_version = candidate.law_version" in predicate


def test_postgres_stats_count_latest_indexed_chunks() -> None:
    cursor = _RecordingCursor(
        fetchone_results=[{"chunks": 4, "documents": 2}]
    )
    store = object.__new__(PostgresGraphRAGStore)
    store.connection = _RecordingConnection(cursor)

    result = store.stats()

    query = cursor.queries[0][0]
    assert result["chunks"] == 4
    assert "current_chunk.law_status IN" not in query
    assert "latest_law.latest_version = current_chunk.law_version" in query


def test_postgres_vector_and_bm25_paths_use_latest_indexed_versions(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        graphrag_module,
        "postgres_dense_vector",
        lambda *_: [0.1, 0.2],
    )
    vector_cursor = _RecordingCursor(fetchall_results=[[]])
    vector_store = object.__new__(PostgresGraphRAGStore)
    vector_store.connection = _RecordingConnection(vector_cursor)
    vector_store.config = SimpleNamespace(postgres_vector_size=2)

    assert vector_store._vector_candidates("thuế", 5) == []
    vector_query = vector_cursor.queries[0][0]
    assert "current_chunk.law_status IN" not in vector_query
    assert "latest_law.latest_version = current_chunk.law_version" in vector_query

    monkeypatch.setattr(
        graphrag_module,
        "postgres_dense_vector",
        lambda *_: None,
    )
    no_dense_cursor = _RecordingCursor(fetchall_results=[[]])
    vector_store.connection = _RecordingConnection(no_dense_cursor)

    assert vector_store._vector_candidates("thuế", 5) == []
    assert no_dense_cursor.queries == []

    row = {
        **_row("current", "thuế phải nộp"),
        "_fts_score": 1.0,
        "law_code": "200/2025/QH15",
        "law_status": "IN_FORCE",
        "law_version": 2,
    }
    bm25_cursor = _RecordingCursor(fetchall_results=[[row]])
    bm25_store = object.__new__(PostgresGraphRAGStore)
    bm25_store.connection = _RecordingConnection(bm25_cursor)
    bm25_store._bm25_corpus_statistics = None
    bm25_store.config = SimpleNamespace(bm25_k1=1.5, bm25_b=0.75)

    candidates = bm25_store._bm25_candidates("thuế", 5)
    assert candidates[0]["_bm25_score"] == 1.0
    candidate_query = bm25_cursor.queries[0][0]
    assert "current_chunk.law_status IN" not in candidate_query
    assert "graphrag_law_version AS latest_law" in candidate_query
    assert len(bm25_cursor.queries) == 1


def test_neo4j_candidate_and_expansion_paths_use_latest_indexed_versions() -> None:
    driver = _GraphDriver()
    plain = object.__new__(Neo4jGraphRAGStore)
    plain.driver = driver
    plain.config = SimpleNamespace(neo4j_database="neo4j")

    assert plain._neo4j_candidates("thuế", 5) == []
    assert plain._chunks_for_nodes(["node-1"]) == []

    hybrid = object.__new__(Neo4jPostgresGraphRAGStore)
    hybrid.driver = driver
    hybrid.config = SimpleNamespace(neo4j_database="neo4j")
    assert hybrid._chunks_for_nodes(["node-1"]) == []

    assert len(driver.recording_session.calls) == 3
    for query, parameters in driver.recording_session.calls:
        assert "law_status IN $current_statuses" not in query
        assert "coalesce(" in query
        assert "newer_document.version > document.version" in query
        assert "current_statuses" not in parameters
