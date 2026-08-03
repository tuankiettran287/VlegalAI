from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.api import _evidence_gated_sources
from app.services.ai import GeminiError
from app.services.evidence_gate import _schema, assess_source_relevance


def _sources() -> list[dict]:
    return [
        {
            "source_id": "S1",
            "citation": "Nguồn một",
            "title": "Quy định gần nghĩa",
            "text": "Nguồn có cùng chủ thể nhưng quy định một đại lượng khác.",
        },
        {
            "source_id": "S2",
            "citation": "Nguồn hai",
            "title": "Quy định trực tiếp",
            "text": "Nguồn trực tiếp quy định đúng đại lượng được hỏi.",
        },
    ]


def test_evidence_gate_keeps_only_direct_sources() -> None:
    class _AI:
        async def complete_json(self, *_: object, **__: object) -> dict:
            return {
                "relevant_source_ids": ["S2"],
                "coverage": "sufficient",
                "refined_search_query": "",
                "reason": "S2 trực tiếp hỗ trợ đúng đại lượng.",
            }

    result = asyncio.run(
        assess_source_relevance(
            _AI(),  # type: ignore[arg-type]
            original_question="Đại lượng được hỏi là bao nhiêu?",
            retrieval_query="Đại lượng pháp lý cần xác định",
            sources=_sources(),
            timeout_seconds=2,
        )
    )

    assert result.relevant_source_ids == ("S2",)
    assert result.coverage == "sufficient"
    assert result.failed is False


def test_evidence_gate_returns_safe_refined_query_when_sources_miss_intent() -> None:
    class _AI:
        async def complete_json(self, *_: object, **__: object) -> dict:
            return {
                "relevant_source_ids": [],
                "coverage": "none",
                "refined_search_query": "Thuật ngữ pháp lý đúng của đại lượng cần tìm",
                "reason": "Các nguồn hiện tại chỉ cùng bối cảnh.",
            }

    result = asyncio.run(
        assess_source_relevance(
            _AI(),  # type: ignore[arg-type]
            original_question="Đại lượng hiện tại là bao nhiêu?",
            retrieval_query="Cách gọi đời thường của đại lượng",
            sources=_sources(),
            timeout_seconds=2,
        )
    )

    assert result.relevant_source_ids == ()
    assert result.coverage == "none"
    assert result.refined_search_query == (
        "Thuật ngữ pháp lý đúng của đại lượng cần tìm"
    )


def test_evidence_gate_distinguishes_related_sources_from_direct_sources() -> None:
    class _AI:
        async def complete_json(self, *_: object, **__: object) -> dict:
            return {
                "relevant_source_ids": [],
                "related_source_ids": ["S2"],
                "coverage": "partial",
                "refined_search_query": "",
                "reason": "Nguồn giải thích phần liên quan nhưng thiếu giá trị được hỏi.",
            }

    result = asyncio.run(
        assess_source_relevance(
            _AI(),  # type: ignore[arg-type]
            original_question="Giá trị hiện tại là bao nhiêu?",
            retrieval_query="Giá trị hiện tại",
            sources=_sources(),
            timeout_seconds=2,
        )
    )

    assert result.relevant_source_ids == ()
    assert result.related_source_ids == ("S2",)
    assert result.coverage == "partial"


def test_evidence_gate_rejects_refinement_that_invents_a_number() -> None:
    class _AI:
        async def complete_json(self, *_: object, **__: object) -> dict:
            return {
                "relevant_source_ids": [],
                "coverage": "none",
                "refined_search_query": "Tìm quy định có giá trị 12345 đồng",
                "reason": "Không đủ nguồn.",
            }

    result = asyncio.run(
        assess_source_relevance(
            _AI(),  # type: ignore[arg-type]
            original_question="Mức áp dụng là bao nhiêu?",
            retrieval_query="Mức áp dụng hiện tại",
            sources=_sources(),
            timeout_seconds=2,
        )
    )

    assert result.refined_search_query == ""


def test_evidence_gate_fails_safely_when_model_is_unavailable() -> None:
    class _AI:
        async def complete_json(self, *_: object, **__: object) -> dict:
            raise GeminiError("unavailable")

    result = asyncio.run(
        assess_source_relevance(
            _AI(),  # type: ignore[arg-type]
            original_question="Quyền của người lao động là gì?",
            retrieval_query="Quyền của người lao động",
            sources=_sources(),
            timeout_seconds=2,
        )
    )

    assert result.relevant_source_ids == ()
    assert result.failed is True
    assert result.reason == "ai_unavailable_safe_fallback"


def test_related_source_ids_remain_optional_for_vertex_responses() -> None:
    schema = _schema(["S1", "S2"])

    assert "related_source_ids" in schema["properties"]
    assert "related_source_ids" not in schema["required"]


def test_api_evidence_gate_drops_semantic_only_context_when_gate_is_unavailable() -> None:
    class _AI:
        async def complete_json(self, *_: object, **__: object) -> dict:
            raise GeminiError("unavailable")

    sources = _sources()
    for source in sources:
        source["reasons"] = ["intent_anchor_semantic_fallback"]
    settings = SimpleNamespace(
        evidence_gate_enabled=True,
        evidence_gate_timeout_seconds=2.0,
        evidence_gate_max_sources=8,
    )

    selected, verification, query = asyncio.run(
        _evidence_gated_sources(
            original_question="Cách gọi đời thường của khái niệm là gì?",
            retrieval_query="Cách gọi đời thường của khái niệm",
            sources=sources,
            verification={"checked": True, "all_current": True},
            ai=_AI(),  # type: ignore[arg-type]
            retrieval=None,  # type: ignore[arg-type]
            freshness=None,  # type: ignore[arg-type]
            settings=settings,  # type: ignore[arg-type]
        )
    )

    assert selected == []
    assert verification["all_current"] is True
    assert "chỉ hỗ trợ một phần" in verification["note"]
    assert query == "Cách gọi đời thường của khái niệm"


def test_api_evidence_gate_keeps_deterministic_context_when_gate_is_unavailable() -> None:
    class _AI:
        async def complete_json(self, *_: object, **__: object) -> dict:
            raise GeminiError("unavailable")

    sources = _sources()
    for source in sources:
        source["reasons"] = ["ontology_concept_match", "postgres_bm25"]
    settings = SimpleNamespace(
        evidence_gate_enabled=True,
        evidence_gate_timeout_seconds=2.0,
        evidence_gate_max_sources=8,
    )

    selected, verification, _ = asyncio.run(
        _evidence_gated_sources(
            original_question="Người lao động có quyền yêu cầu công ty giải quyết không?",
            retrieval_query="Quyền yêu cầu của người lao động",
            sources=sources,
            verification={"checked": True, "all_current": True},
            ai=_AI(),  # type: ignore[arg-type]
            retrieval=None,  # type: ignore[arg-type]
            freshness=None,  # type: ignore[arg-type]
            settings=settings,  # type: ignore[arg-type]
        )
    )

    assert [source["source_id"] for source in selected] == ["S1", "S2"]
    assert "chỉ hỗ trợ một phần" in verification["note"]


def test_api_evidence_gate_requires_direct_value_when_gate_is_unavailable() -> None:
    class _AI:
        async def complete_json(self, *_: object, **__: object) -> dict:
            raise GeminiError("unavailable")

    sources = [
        {
            "source_id": "S1",
            "citation": "Điều 5 Nghị định thử nghiệm",
            "title": "Mức tham chiếu",
            "text": "Mức tham chiếu được áp dụng theo mức lương cơ sở.",
            "reasons": ["ontology_concept_match", "postgres_bm25"],
        },
        {
            "source_id": "S2",
            "citation": "Điều 3 Nghị định trực tiếp",
            "title": "Mức lương cơ sở",
            "text": "Mức lương cơ sở là 2.340.000 đồng/tháng.",
            "reasons": ["ontology_concept_match", "postgres_bm25"],
        },
    ]
    settings = SimpleNamespace(
        evidence_gate_enabled=True,
        evidence_gate_timeout_seconds=2.0,
        evidence_gate_max_sources=8,
    )

    selected, _, _ = asyncio.run(
        _evidence_gated_sources(
            original_question="Mức lương cơ sở hiện nay là bao nhiêu?",
            retrieval_query="Mức lương cơ sở",
            sources=sources,
            verification={"checked": True, "all_current": True},
            ai=_AI(),  # type: ignore[arg-type]
            retrieval=None,  # type: ignore[arg-type]
            freshness=None,  # type: ignore[arg-type]
            settings=settings,  # type: ignore[arg-type]
        )
    )

    assert [source["source_id"] for source in selected] == ["S1"]
    assert "2.340.000 đồng/tháng" in selected[0]["text"]


def test_api_evidence_gate_preserves_retrieved_context_when_gate_selects_none() -> None:
    class _AI:
        async def complete_json(self, *_: object, **__: object) -> dict:
            return {
                "relevant_source_ids": [],
                "related_source_ids": [],
                "coverage": "none",
                "refined_search_query": "",
                "reason": "Không có nguồn định nghĩa nguyên văn.",
            }

    sources = _sources()
    for source in sources:
        source["reasons"] = ["intent_anchors:2", "postgres_bm25"]
    settings = SimpleNamespace(
        evidence_gate_enabled=True,
        evidence_gate_timeout_seconds=2.0,
        evidence_gate_max_sources=8,
    )

    selected, verification, query = asyncio.run(
        _evidence_gated_sources(
            original_question="Khái niệm này là gì?",
            retrieval_query="Khái niệm này",
            sources=sources,
            verification={"checked": True, "all_current": True},
            ai=_AI(),  # type: ignore[arg-type]
            retrieval=None,  # type: ignore[arg-type]
            freshness=None,  # type: ignore[arg-type]
            settings=settings,  # type: ignore[arg-type]
        )
    )

    assert len(selected) == 2
    assert [source["source_id"] for source in selected] == ["S1", "S2"]
    assert verification["note"] != "Dữ liệu không có sẵn"
    assert "chỉ hỗ trợ một phần" in verification["note"]
    assert query == "Khái niệm này"


def test_api_evidence_gate_refines_retrieval_after_off_topic_sources() -> None:
    class _AI:
        def __init__(self) -> None:
            self.calls = 0

        async def complete_json(self, *_: object, **__: object) -> dict:
            self.calls += 1
            if self.calls == 1:
                return {
                    "relevant_source_ids": [],
                    "coverage": "none",
                    "refined_search_query": "Khái niệm pháp lý chính xác cần tìm",
                    "reason": "Nguồn đầu tiên chỉ cùng bối cảnh.",
                }
            return {
                "relevant_source_ids": ["S1"],
                "coverage": "sufficient",
                "refined_search_query": "",
                "reason": "Nguồn mới trực tiếp hỗ trợ câu hỏi.",
            }

    class _Retrieval:
        def __init__(self) -> None:
            self.queries: list[str] = []

        async def retrieve(self, query: str) -> list[dict]:
            self.queries.append(query)
            return [
                {
                    "source_id": "S9",
                    "citation": "Nguồn sau truy vấn tinh chỉnh",
                    "title": "Quy định trực tiếp",
                    "text": "Căn cứ trực tiếp cho đúng khái niệm cần tìm.",
                }
            ]

    ai = _AI()
    retrieval = _Retrieval()
    initial_sources = _sources()
    for source in initial_sources:
        source["reasons"] = ["intent_anchor_semantic_fallback"]
    settings = SimpleNamespace(
        evidence_gate_enabled=True,
        evidence_gate_timeout_seconds=2.0,
        evidence_gate_max_sources=8,
    )

    sources, verification, query = asyncio.run(
        _evidence_gated_sources(
            original_question="Cách gọi đời thường của khái niệm là gì?",
            retrieval_query="Cách gọi đời thường của khái niệm",
            sources=initial_sources,
            verification={"checked": True, "all_current": True},
            ai=ai,  # type: ignore[arg-type]
            retrieval=retrieval,  # type: ignore[arg-type]
            freshness=None,  # type: ignore[arg-type]
            settings=settings,  # type: ignore[arg-type]
        )
    )

    assert ai.calls == 2
    assert retrieval.queries == ["Khái niệm pháp lý chính xác cần tìm"]
    assert query == "Khái niệm pháp lý chính xác cần tìm"
    assert len(sources) == 1
    assert sources[0]["source_id"] == "S1"
    assert verification["checked"] is True
