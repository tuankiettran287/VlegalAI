from __future__ import annotations

from types import SimpleNamespace

from app.external_graphrag import (
    PostgresGraphRAGStore,
    bm25_score,
    postgres_lexical_terms,
    postgres_or_tsquery,
    reciprocal_rank_fusion,
)


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
