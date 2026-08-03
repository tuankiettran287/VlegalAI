from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.api import (
    _complete_with_citation_repair,
    _legal_sources,
    _validate_answer_plan_coverage,
)
from app.services.ai import GeminiError, LEGAL_SYSTEM_PROMPT
from app.services import retrieval as retrieval_module
from app.services.retrieval import (
    RetrievalService,
    append_detailed_citations,
    build_answer_plan,
    build_context,
    classify_retrieval_route,
    format_source_inline_locator,
    format_source_locator,
    format_source_opening,
    plan_retrieval_queries,
)


def _source(
    source_id: str = "S1",
    *,
    citation: str = (
        "Bộ Luật Lao Động (45/2019/QH14) > Chương VII > "
        "Điều 98. Tiền lương làm thêm giờ > Khoản 1 > Điểm c"
    ),
    text: str = "Ngày nghỉ lễ, tết được trả ít nhất bằng 300%.",
) -> dict:
    return {
        "source_id": source_id,
        "chunk_id": f"chunk-{source_id}",
        "doc_id": "bo-luat-lao-dong",
        "node_id": f"node-{source_id}",
        "chunk_type": "point",
        "title": "Điểm c khoản 1 Điều 98",
        "citation": citation,
        "text": text,
        "score": 1.0,
        "reasons": ["test"],
    }


def test_compound_question_is_split_and_keeps_focus_actor() -> None:
    wage_question = "Lương cơ bản là bao nhiêu và khi làm lễ thì nhân mấy?"
    actor_question = "Bạn tôi giết người và tôi bao che thì tôi bị lỗi gì?"

    wage_queries = plan_retrieval_queries(wage_question)
    actor_plan = build_answer_plan(actor_question)

    assert len(wage_queries) >= 3
    assert any("lương cơ bản là bao nhiêu" in query.lower() for query in wage_queries)
    assert any("làm lễ" in query.lower() for query in wage_queries)
    assert actor_plan["mode"] == "multi_hop"
    assert actor_plan["actors"] == ["bạn tôi", "tôi"]
    assert actor_plan["focus_actor"] == "tôi"
    assert len(actor_plan["must_answer"]) == 2


def test_planner_does_not_inject_an_adjacent_concept_for_unmapped_question() -> None:
    query = (
        "Mức lương cơ bản hiện tại của cán bộ nhà nước "
        "là bao nhiêu?"
    )

    planned = plan_retrieval_queries(query)
    answer_plan = build_answer_plan(query)

    assert planned == [query]
    assert "target_concept" not in answer_plan
    assert "do_not_confuse_with" not in answer_plan


def test_ontology_expands_specific_concepts_instead_of_broad_wage_terms() -> None:
    query = (
        "tăng ca ban đêm thì lương nhận được "
        "gấp bao nhiêu lần lương cơ bản"
    )

    planned = plan_retrieval_queries(query)
    answer_plan = build_answer_plan(query)

    assert any(
        "Tiền lương làm thêm giờ" in item
        and "150%" in item
        and "300%" in item
        for item in planned[1:]
    )
    assert any(
        "Tiền lương làm việc vào ban đêm" in item
        and "30%" in item
        and "20%" in item
        for item in planned[1:]
    )
    assert all("mức lương tối thiểu Điều 90 Điều 91" not in item for item in planned)
    assert {
        concept["label"]
        for concept in answer_plan["required_concepts"]
    } == {
        "Tiền lương làm thêm giờ",
        "Tiền lương làm việc vào ban đêm",
    }


def test_long_safety_scenario_focuses_on_the_explicit_legal_question() -> None:
    query = (
        "Vì mưu sinh chị H ký hợp đồng làm công nhân khai thác đá. "
        "Tại công trường, chị thấy việc nổ mìn có nguy cơ đá văng, đá lở "
        "đe dọa tính mạng, sức khỏe nên từ chối làm việc. Chủ doanh nghiệp "
        "cho rằng đã ký hợp đồng thì không được từ chối. Theo quy định pháp "
        "luật, chị H có được từ chối làm việc không?"
    )

    answer_plan = build_answer_plan(query)
    planned = plan_retrieval_queries(query)

    assert answer_plan["question_focus"] == (
        "Theo quy định pháp luật, chị H có được từ chối làm việc không?"
    )
    assert answer_plan["must_answer"] == [answer_plan["question_focus"]]
    assert {
        concept["label"]
        for concept in answer_plan["required_concepts"]
    } == {
        "Quyền từ chối hoặc rời bỏ nơi làm việc không bảo đảm an toàn"
    }
    assert any(
        "nguy cơ tai nạn lao động" in item
        and "tính mạng hoặc sức khỏe" in item
        for item in planned[1:]
    )


def test_concept_filter_rejects_adjacent_sources_and_keeps_direct_rules() -> None:
    query = (
        "tăng ca ban đêm thì lương nhận được "
        "gấp bao nhiêu lần lương cơ bản"
    )

    class _Store:
        def retrieve(self, _: str, __: int) -> list[dict]:
            return [
                _source(
                    "S1",
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > "
                        "Điều 91. Mức lương tối thiểu"
                    ),
                    text="Mức lương tối thiểu được xác lập theo vùng.",
                ),
                _source(
                    "S2",
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > "
                        "Điều 98. Tiền lương làm thêm giờ > Khoản 1"
                    ),
                    text=(
                        "Tiền lương làm thêm giờ ít nhất bằng 150% vào ngày "
                        "thường, 200% ngày nghỉ và 300% ngày lễ, tết."
                    ),
                ),
                _source(
                    "S3",
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > "
                        "Điều 98. Tiền lương làm thêm giờ > Khoản 2"
                    ),
                    text=(
                        "Người lao động làm việc vào ban đêm được trả thêm "
                        "ít nhất bằng 30%."
                    ),
                ),
                _source(
                    "S4",
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > "
                        "Điều 98. Tiền lương làm thêm giờ > Khoản 3"
                    ),
                    text=(
                        "Người lao động làm thêm giờ vào ban đêm còn được "
                        "trả thêm 20% tiền lương."
                    ),
                ),
            ]

    service = RetrievalService(SimpleNamespace(retrieval_top_k=10))
    service._store = _Store()

    rows = asyncio.run(service.retrieve(query))

    assert len(rows) == 3
    assert all("Điều 98" in row["citation"] for row in rows)
    assert all("Điều 91" not in row["citation"] for row in rows)


def test_answer_plan_rejects_cited_but_off_topic_answer() -> None:
    answer_plan = build_answer_plan(
        "tăng ca ban đêm thì lương nhận được "
        "gấp bao nhiêu lần lương cơ bản"
    )

    with pytest.raises(GeminiError, match="chưa giải quyết đúng khái niệm"):
        _validate_answer_plan_coverage(
            (
                "Theo Điều 91 Bộ luật Lao động, mức lương tối thiểu "
                "được xác lập theo vùng [S1]."
            ),
            answer_plan,
        )

    _validate_answer_plan_coverage(
        (
            "Theo Điều 98 Bộ luật Lao động, tiền lương làm thêm giờ "
            "vào ban đêm phải gồm các khoản trả thêm tương ứng [S1]."
        ),
        answer_plan,
    )


def test_generic_intent_coverage_keeps_context_and_rejects_adjacent_results() -> None:
    class _Store:
        def retrieve(self, _: str, __: int) -> list[dict]:
            return [
                _source(
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > Chương VI > "
                        "Điều 91. Mức lương tối thiểu"
                    ),
                    text=(
                        "Mức lương tối thiểu được xác lập theo vùng, "
                        "ấn định theo tháng, giờ."
                    ),
                ),
                _source(
                    "S2",
                    citation=(
                        "Luật Cán Bộ, Công Chức (80/2025/QH15) > "
                        "Điều 41. Chính sách đối với công chức"
                    ),
                    text=(
                        "Nhà nước thực hiện chính sách tiền lương "
                        "đối với cán bộ, công chức."
                    ),
                ),
            ]

    service = RetrievalService(SimpleNamespace(retrieval_top_k=10))
    service._store = _Store()

    rows = asyncio.run(
        service.retrieve(
            "Mức lương cơ bản hiện tại của cán bộ nhà nước là bao nhiêu?"
        )
    )

    assert len(rows) == 1
    assert "cán bộ, công chức" in rows[0]["text"]
    assert "tối thiểu" not in rows[0]["text"]
    assert any(
        reason.startswith("intent_terms:")
        for reason in rows[0]["reasons"]
    )


def test_generic_intent_filter_does_not_require_a_number_in_the_same_chunk() -> None:
    query = "Lương cơ sở của công chức hiện nay là bao nhiêu?"

    class _Store:
        def __init__(self, text: str) -> None:
            self.text = text

        def retrieve(self, _: str, __: int) -> list[dict]:
            return [
                _source(
                    citation=(
                        "Nghị định thử nghiệm (73/2024/NĐ-CP) > "
                        "Điều 3. Mức lương cơ sở"
                    ),
                    text=self.text,
                )
            ]

    incomplete = RetrievalService(SimpleNamespace(retrieval_top_k=10))
    incomplete._store = _Store(
        "Mức lương cơ sở được dùng để tính tiền lương trong bảng lương."
    )
    complete = RetrievalService(SimpleNamespace(retrieval_top_k=10))
    complete._store = _Store(
        "Mức lương cơ sở là 2,34 triệu đồng/tháng."
    )

    incomplete_rows = asyncio.run(incomplete.retrieve(query))
    assert len(incomplete_rows) == 1
    assert any(
        reason.startswith("intent_terms:")
        for reason in incomplete_rows[0]["reasons"]
    )
    rows = asyncio.run(complete.retrieve(query))
    assert len(rows) == 1
    assert "2,34 triệu đồng/tháng" in rows[0]["text"]
    assert any(
        reason.startswith("intent_terms:")
        for reason in rows[0]["reasons"]
    )


def test_sparse_single_hop_retrieval_retries_with_a_wider_generic_pool() -> None:
    query = (
        "Người lao động muốn đơn phương chấm dứt hợp đồng lao động "
        "thì phải báo trước bao lâu?"
    )

    class _Store:
        def __init__(self) -> None:
            self.limits: list[int] = []

        def retrieve(self, _: str, limit: int) -> list[dict]:
            self.limits.append(limit)
            if limit <= 8:
                return [
                    _source(
                        citation="Bộ Luật Lao Động > Điều 91",
                        text="Mức lương tối thiểu được xác lập theo vùng.",
                    )
                ]
            return [
                _source(
                    citation="Bộ Luật Lao Động > Điều 35",
                    text=(
                        "Người lao động có quyền đơn phương chấm dứt hợp đồng "
                        "lao động nhưng phải báo trước theo thời hạn luật định."
                    ),
                )
            ]

    service = RetrievalService(SimpleNamespace(retrieval_top_k=10))
    store = _Store()
    service._store = store

    rows = asyncio.run(service.retrieve(query))

    assert store.limits[0] == 8
    assert store.limits[-1] > store.limits[0]
    assert len(rows) == 1
    assert "đơn phương chấm dứt" in rows[0]["text"]


def test_short_forced_labor_query_expands_to_definition_and_prohibition() -> None:
    queries = plan_retrieval_queries("Cưỡng bức lao động")

    assert queries[0] == "Cưỡng bức lao động"
    assert classify_retrieval_route("Cưỡng bức lao động") == "single_hop"
    assert build_answer_plan("Cưỡng bức lao động")["mode"] == "single_hop"
    assert any(
        "Điều 3" in query
        and "Điều 8" in query
        and "45/2019/QH14" in query
        for query in queries[1:]
    )


def test_short_forced_labor_query_retrieves_expanded_legal_definition() -> None:
    class _Store:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def retrieve(self, query: str, _: int) -> list[dict]:
            self.queries.append(query)
            if "Điều 3" not in query:
                return []
            return [
                _source(
                    "S2",
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > Chương I > "
                        "Điều 3. Giải thích từ ngữ > Khoản 1"
                    ),
                    text=(
                        "Người lao động là người làm việc cho người sử dụng "
                        "lao động theo thỏa thuận và được trả lương."
                    ),
                ),
                _source(
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > Chương I > "
                        "Điều 3. Giải thích từ ngữ > Khoản 7"
                    ),
                    text=(
                        "Cưỡng bức lao động là việc dùng vũ lực, đe dọa dùng "
                        "vũ lực hoặc các thủ đoạn khác để ép buộc người lao động."
                    ),
                )
            ]

    store = _Store()
    service = RetrievalService(SimpleNamespace(retrieval_top_k=10))
    service._store = store

    rows = asyncio.run(service.retrieve("Cưỡng bức lao động"))

    assert store.queries == plan_retrieval_queries("Cưỡng bức lao động")
    assert len(rows) == 1
    assert "Cưỡng bức lao động" in rows[0]["text"]


def test_forced_labor_definition_keeps_only_definition_and_prohibition() -> None:
    class _Store:
        def retrieve(self, _: str, __: int) -> list[dict]:
            return [
                _source(
                    "S1",
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > "
                        "Điều 8. Các hành vi bị nghiêm cấm"
                    ),
                    text=(
                        "Điều 8. Các hành vi bị nghiêm cấm. "
                        "Ngược đãi người lao động, cưỡng bức lao động."
                    ),
                ),
                _source(
                    "S2",
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > "
                        "Điều 8. Các hành vi bị nghiêm cấm > Khoản 2"
                    ),
                    text="Ngược đãi người lao động, cưỡng bức lao động.",
                ),
                _source(
                    "S3",
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > "
                        "Điều 3. Giải thích từ ngữ > Khoản 7"
                    ),
                    text=(
                        "Cưỡng bức lao động là việc dùng vũ lực, đe dọa "
                        "dùng vũ lực hoặc thủ đoạn khác để ép buộc làm việc."
                    ),
                ),
                _source(
                    "S4",
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > "
                        "Điều 165. Người giúp việc gia đình > Khoản 1"
                    ),
                    text="Cấm cưỡng bức lao động đối với người giúp việc.",
                ),
                _source(
                    "S5",
                    citation=(
                        "Luật Người Lao Động Việt Nam Đi Làm Việc Ở "
                        "Nước Ngoài (69/2020/QH14) > Điều 3 > Khoản 5"
                    ),
                    text=(
                        "Cưỡng bức lao động là việc dùng vũ lực để "
                        "ép buộc người lao động làm việc trái ý muốn."
                    ),
                ),
            ]

    service = RetrievalService(SimpleNamespace(retrieval_top_k=10))
    service._store = _Store()

    rows = asyncio.run(service.retrieve("Cưỡng bức lao động là gì?"))

    assert len(rows) == 2
    assert "Điều 3" in rows[0]["citation"]
    assert "45/2019/QH14" in rows[0]["citation"]
    assert "Khoản 2" in rows[1]["citation"]
    assert all("69/2020/QH14" not in row["citation"] for row in rows)


def test_retrieval_route_distinguishes_single_hop_and_graph_questions() -> None:
    assert (
        classify_retrieval_route(
            "Mức lương tối thiểu vùng hiện nay là bao nhiêu?"
        )
        == "single_hop"
    )
    assert (
        classify_retrieval_route(
            "Nếu công ty chậm trả lương thì người lao động có quyền gì?"
        )
        == "multi_hop"
    )
    assert (
        classify_retrieval_route(
            "Phân tích toàn bộ quyền và nghĩa vụ của các bên trong hợp đồng lao động"
        )
        == "multi_abstract"
    )


def test_single_hop_never_initializes_graph_store(
    monkeypatch,
) -> None:
    class _Store:
        def __init__(self, label: str) -> None:
            self.label = label
            self.queries: list[str] = []

        def retrieve(self, query: str, _: int) -> list[dict]:
            self.queries.append(query)
            return [
                _source(
                    text=(
                        "Cưỡng bức lao động là hành vi bị nghiêm cấm "
                        "trong quan hệ lao động."
                    ),
                )
            ]

    postgres = _Store("postgres")
    graph = _Store("graph")
    graph_initializations = 0

    def postgres_factory(_: object) -> _Store:
        return postgres

    def graph_factory(_: object) -> _Store:
        nonlocal graph_initializations
        graph_initializations += 1
        return graph

    monkeypatch.setattr(retrieval_module, "_external_config", lambda _: object())
    monkeypatch.setattr(
        retrieval_module,
        "PostgresGraphRAGStore",
        postgres_factory,
    )
    monkeypatch.setattr(
        retrieval_module,
        "Neo4jPostgresGraphRAGStore",
        graph_factory,
    )
    service = RetrievalService(
        SimpleNamespace(
            retriever_backend="hybrid_rag",
            retrieval_top_k=10,
        )
    )

    rows = asyncio.run(service.retrieve("Cưỡng bức lao động"))

    assert rows
    assert postgres.queries == plan_retrieval_queries("Cưỡng bức lao động")
    assert graph.queries == []
    assert graph_initializations == 0
    assert "retrieval_route:single_hop" in rows[0]["reasons"]


def test_multi_hop_uses_graph_store(
    monkeypatch,
) -> None:
    class _Store:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def retrieve(self, query: str, _: int) -> list[dict]:
            self.queries.append(query)
            return [
                _source(
                    text=(
                        "Công ty chậm trả lương làm phát sinh quyền yêu cầu "
                        "trả đủ tiền lương của người lao động."
                    ),
                )
            ]

    postgres = _Store()
    graph = _Store()
    monkeypatch.setattr(retrieval_module, "_external_config", lambda _: object())
    monkeypatch.setattr(
        retrieval_module,
        "PostgresGraphRAGStore",
        lambda _: postgres,
    )
    monkeypatch.setattr(
        retrieval_module,
        "Neo4jPostgresGraphRAGStore",
        lambda _: graph,
    )
    service = RetrievalService(
        SimpleNamespace(
            retriever_backend="hybrid_rag",
            retrieval_top_k=10,
        )
    )
    query = "Nếu công ty chậm trả lương thì người lao động có quyền gì?"

    rows = asyncio.run(service.retrieve(query))

    assert rows
    assert postgres.queries == []
    assert graph.queries == plan_retrieval_queries(query)
    assert "retrieval_route:multi_hop" in rows[0]["reasons"]


def test_retrieval_runs_each_compound_facet_and_merges_results() -> None:
    class _Store:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def retrieve(self, query: str, _: int) -> list[dict]:
            self.queries.append(query)
            if "làm lễ" in query.lower():
                return [_source("S2")]
            return [
                _source(
                    "S1",
                    citation=(
                        "Bộ Luật Lao Động (45/2019/QH14) > Chương VI > "
                        "Điều 91. Mức lương tối thiểu"
                    ),
                    text="Mức lương tối thiểu được xác lập theo vùng.",
                )
            ]

    store = _Store()
    service = RetrievalService(SimpleNamespace(retrieval_top_k=10))
    service._store = store
    rows = asyncio.run(
        service.retrieve(
            "Lương cơ bản là bao nhiêu và khi làm lễ thì nhân mấy?"
        )
    )

    assert store.queries == plan_retrieval_queries(
        "Lương cơ bản là bao nhiêu và khi làm lễ thì nhân mấy?"
    )
    assert {row["node_id"] for row in rows} == {"node-S1", "node-S2"}


def test_out_of_scope_vector_results_are_rejected() -> None:
    class _Store:
        def retrieve(self, _: str, __: int) -> list[dict]:
            return [
                _source(
                    text=(
                        "Người lao động có quyền hưởng tiền lương theo "
                        "Bộ luật Lao động; vi phạm nghiêm trọng có thể bị "
                        "truy cứu trách nhiệm hình sự."
                    )
                )
            ]

    service = RetrievalService(SimpleNamespace(retrieval_top_k=10))
    service._store = _Store()
    rows = asyncio.run(
        service.retrieve(
            "Bạn tôi giết người và tôi bao che thì tôi bị tội gì?"
        )
    )

    assert rows == []


def test_hallucinated_instrument_name_triggers_grounded_repair() -> None:
    class _AI:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, *_: object, **__: object) -> str:
            self.calls += 1
            return "Theo Bộ luật Hình sự, bạn có thể bị xử lý [S1]."

        async def complete_json(self, *_: object, **__: object) -> dict:
            self.calls += 1
            return {
                "statements": [
                    {
                        "text": (
                            "Theo Điều 98 Bộ luật Lao động số "
                            "45/2019/QH14, mức tối thiểu là 300%."
                        ),
                        "citations": ["S1"],
                    }
                ]
            }

    ai = _AI()
    source = _source()
    answer = asyncio.run(
        _complete_with_citation_repair(
            ai,
            "system",
            "prompt",
            allowed_ids=["S1"],
            sources=[source],
            max_tokens=300,
        )
    )

    assert ai.calls == 2
    assert answer.startswith("Theo ")
    assert "Bộ luật Hình sự" not in answer
    assert "Bộ luật Lao động" in answer
    assert "[S1]" in answer


def test_citation_catalog_uses_article_clause_point_document_and_issuer() -> None:
    source = _source()

    locator = format_source_locator(source)
    answer = append_detailed_citations("Mức tối thiểu là 300% [S1].", [source])

    assert locator == (
        "Điều 98, khoản 1, điểm c, Bộ Luật Lao Động số "
        "45/2019/QH14, do Quốc hội ban hành"
    )
    assert f"- Theo {locator} [S1]." in answer


def test_answer_context_uses_concise_inline_citation() -> None:
    source = {
        **_source(),
        "law_status": "IN_FORCE",
        "law_checked_at": "2026-07-28T08:30:00+07:00",
    }

    locator = format_source_inline_locator(source)
    context = build_context([source])

    assert locator == (
        "Điều 98, khoản 1, điểm c, Bộ Luật Lao Động số "
        "45/2019/QH14"
    )
    assert f"Theo {locator} [S1]" in context
    assert "do Quốc hội ban hành" not in context
    assert "đang được xác nhận còn hiệu lực" not in context


def test_source_opening_distinguishes_effective_and_verification_dates() -> None:
    source = _source()

    effective_opening = format_source_opening(
        {
            **source,
            "effective_date": "2021-01-01",
            "law_status": "IN_FORCE",
            "law_checked_at": "2026-07-27T08:30:00+07:00",
        }
    )
    verified_opening = format_source_opening(
        {
            **source,
            "law_status": "IN_FORCE",
            "law_checked_at": "2026-07-27T08:30:00+07:00",
        }
    )
    unknown_opening = format_source_opening(
        {
            **source,
            "law_status": "IN_FORCE",
        }
    )

    assert effective_opening.endswith("có hiệu lực từ ngày 01/01/2021")
    assert verified_opening.endswith(
        "đang được xác nhận còn hiệu lực tại ngày 27/07/2026"
    )
    assert "hiệu lực từ ngày" not in verified_opening
    assert "hiệu lực" not in unknown_opening


def test_legal_prompt_requires_direct_professional_chatbot_opening() -> None:
    normalized_prompt = " ".join(LEGAL_SYSTEM_PROMPT.split())

    assert 'ký tự đầu tiên của câu trả lời phải là “Theo”' in normalized_prompt
    assert "có hiệu lực từ ngày" in normalized_prompt
    assert "không thay bằng một khái niệm gần nghĩa" in normalized_prompt
    assert "Chỉ viện dẫn một hoặc hai nguồn trực tiếp nhất" in normalized_prompt
    assert "focus_actor" in normalized_prompt
    assert "2–4 đoạn ngắn" in normalized_prompt


def test_valid_citations_but_generic_preamble_triggers_style_repair() -> None:
    class _AI:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, *_: object, **__: object) -> str:
            self.calls += 1
            return "Mức tối thiểu bạn được hưởng là 300% [S1]."

        async def complete_json(self, *_: object, **__: object) -> dict:
            self.calls += 1
            return {
                "statements": [
                    {
                        "text": (
                            "Theo Điều 98, khoản 1, điểm c, Bộ luật Lao động "
                            "số 45/2019/QH14, bạn được trả ít nhất 300%."
                        ),
                        "citations": ["S1"],
                    }
                ]
            }

    ai = _AI()
    answer = asyncio.run(
        _complete_with_citation_repair(
            ai,
            "system",
            "prompt",
            allowed_ids=["S1"],
            sources=[_source()],
            max_tokens=300,
        )
    )

    assert ai.calls == 2
    assert answer.startswith("Theo Điều 98")
    assert "[S1]" in answer


def test_grounded_title_matching_ignores_optional_punctuation() -> None:
    class _AI:
        calls = 0

        async def complete(self, *_: object, **__: object) -> str:
            self.calls += 1
            return (
                "Theo Điều 6 Luật An toàn vệ sinh lao động, người lao động "
                "có quyền từ chối công việc nguy hiểm [S1]."
            )

    ai = _AI()
    source = _source(
        citation=(
            "Luật An Toàn, Vệ Sinh Lao Động (84/2015/QH13) > "
            "Điều 6. Quyền và nghĩa vụ về an toàn, vệ sinh lao động"
        ),
        text=(
            "Người lao động có quyền từ chối làm công việc hoặc rời bỏ "
            "nơi làm việc khi thấy rõ nguy cơ xảy ra tai nạn lao động."
        ),
    )

    answer = asyncio.run(
        _complete_with_citation_repair(
            ai,
            "system",
            "prompt",
            allowed_ids=["S1"],
            sources=[source],
            max_tokens=300,
        )
    )

    assert ai.calls == 1
    assert answer.startswith("Theo Điều 6")


def test_safe_draft_is_retained_when_style_repair_hallucinates_a_law() -> None:
    draft = (
        "Người lao động có quyền từ chối công việc có nguy cơ nghiêm trọng "
        "đối với tính mạng hoặc sức khỏe [S1]."
    )

    class _AI:
        calls = 0

        async def complete(self, *_: object, **__: object) -> str:
            self.calls += 1
            return draft

        async def complete_json(self, *_: object, **__: object) -> dict:
            self.calls += 1
            return {
                "statements": [
                    {
                        "text": (
                            "Theo Bộ luật Hình sự số 100/2015/QH13, "
                            "người lao động có quyền từ chối."
                        ),
                        "citations": ["S1"],
                    }
                ]
            }

    ai = _AI()
    source = _source(
        citation=(
            "Luật An Toàn, Vệ Sinh Lao Động (84/2015/QH13) > "
            "Điều 6. Quyền và nghĩa vụ về an toàn, vệ sinh lao động"
        ),
        text=(
            "Người lao động có quyền từ chối làm công việc hoặc rời bỏ "
            "nơi làm việc khi thấy rõ nguy cơ xảy ra tai nạn lao động."
        ),
    )

    answer = asyncio.run(
        _complete_with_citation_repair(
            ai,
            "system",
            "prompt",
            allowed_ids=["S1"],
            sources=[source],
            max_tokens=300,
        )
    )

    assert ai.calls == 2
    assert answer == draft
    assert "Bộ luật Hình sự" not in answer


def test_freshness_limit_counts_laws_instead_of_chunks() -> None:
    rows = [
        {
            **_source(f"S{index}"),
            "citation": (
                "Bộ Luật Lao Động (45/2019/QH14) > "
                f"Điều {index}. Nội dung {index}"
            ),
            "text": f"Nội dung pháp lý Điều {index}.",
        }
        for index in range(1, 21)
    ]

    class _Retrieval:
        async def retrieve(self, _: str) -> list[dict]:
            return [dict(row) for row in rows]

    class _Freshness:
        settings = SimpleNamespace(
            max_laws_verified_per_request=16,
            require_freshness_check=True,
        )

        async def verify_sources(self, sources: list[dict]) -> tuple[object, bool]:
            assert len(sources) == 20
            report = SimpleNamespace(
                items=[
                    SimpleNamespace(
                        code="45/2019/QH14",
                        status="IN_FORCE",
                        source_url="https://vbpl.vn/example",
                    )
                ],
                model_dump=lambda **__: {
                    "checked": True,
                    "all_current": True,
                    "items": [
                        {
                            "code": "45/2019/QH14",
                            "status": "IN_FORCE",
                        }
                    ],
                },
            )
            return report, False

    sources, _ = asyncio.run(
        _legal_sources("Tổng hợp các nghĩa vụ", _Retrieval(), _Freshness())
    )

    assert len(sources) == 20
    assert sources[-1]["source_id"] == "S20"
