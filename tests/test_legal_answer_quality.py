from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.api import (
    _complete_with_citation_repair,
    _legal_sources,
)
from app.services.ai import LEGAL_SYSTEM_PROMPT
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


def test_public_sector_base_salary_is_not_expanded_to_minimum_wage() -> None:
    query = (
        "Mức lương cơ bản hiện tại của cán bộ nhà nước "
        "là bao nhiêu?"
    )

    planned = plan_retrieval_queries(query)
    answer_plan = build_answer_plan(query)

    assert any("mức lương cơ sở" in item for item in planned[1:])
    assert all("mức lương tối thiểu" not in item for item in planned[1:])
    assert answer_plan["target_concept"] == (
        "mức lương cơ sở của cán bộ, công chức, viên chức"
    )
    assert answer_plan["requires_exact_value"] is True
    assert "mức lương tối thiểu vùng" in answer_plan["do_not_confuse_with"]
    assert any(
        "mức lương cơ sở" in item
        for item in plan_retrieval_queries(
            "Mức lương cơ sở hiện nay là bao nhiêu?"
        )[1:]
    )


def test_public_sector_salary_rejects_adjacent_minimum_wage_sources() -> None:
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

    assert rows == []


def test_public_sector_salary_requires_and_accepts_exact_base_amount() -> None:
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

    assert asyncio.run(incomplete.retrieve(query)) == []
    rows = asyncio.run(complete.retrieve(query))
    assert len(rows) == 1
    assert "2,34 triệu đồng/tháng" in rows[0]["text"]


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
    assert "không được thay “mức lương cơ sở/lương cơ bản" in normalized_prompt
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
