from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.api import chat
from app.core.config import Settings
from app.models import ChatMessage, Conversation
from app.schemas import ChatRequest
from app.services.ai import GeminiService
from app.services.chat_effort import chat_effort_profile
from app.services.retrieval import RetrievalService


def test_chat_request_defaults_to_medium_effort() -> None:
    assert ChatRequest(message="Quyền nghỉ phép là gì?").effort == "medium"


def test_chat_request_rejects_unknown_effort() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(message="Quyền nghỉ phép là gì?", effort="extreme")


def test_effort_profiles_have_distinct_cost_and_depth() -> None:
    instant = chat_effort_profile("instant")
    medium = chat_effort_profile("medium")
    high = chat_effort_profile("high")

    assert instant.skip_query_rewrite is True
    assert medium.skip_query_rewrite is False
    assert high.skip_query_rewrite is False
    assert (
        instant.thinking_budget
        < medium.thinking_budget
        < high.thinking_budget
    )
    assert (
        instant.max_output_tokens
        < medium.max_output_tokens
        < high.max_output_tokens
    )
    assert instant.retrieval_query_limit < medium.retrieval_query_limit


@pytest.mark.parametrize(
    ("effort", "expected_budget"),
    [
        ("instant", 0),
        ("medium", 1_024),
        ("high", 4_096),
    ],
)
def test_effort_overrides_vertex_thinking_budget(
    effort: str,
    expected_budget: int,
) -> None:
    service = object.__new__(GeminiService)
    service.settings = SimpleNamespace(
        gemini_model="gemini-2.5-flash",
        gemini_thinking_budget=99,
        gemini_thinking_level="low",
    )
    payload = service._payload(
        "system",
        "question",
        temperature=0.1,
        max_tokens=500,
        json_schema=None,
        thinking_budget=chat_effort_profile(effort).thinking_budget,
    )

    assert payload["generationConfig"]["thinkingConfig"] == {
        "thinkingBudget": expected_budget,
        "includeThoughts": False,
    }


def test_instant_forces_one_direct_retrieval_query() -> None:
    class _Store:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def retrieve(self, query: str, top_k: int) -> list[dict[str, object]]:
            self.calls.append((query, top_k))
            return []

    service = RetrievalService(
        SimpleNamespace(
            retriever_backend="hybrid_rag",
            retrieval_top_k=10,
        )
    )
    store = _Store()
    routes: list[str] = []

    async def get_store(route: str = "single_hop") -> _Store:
        routes.append(route)
        return store

    service._get_store = get_store  # type: ignore[method-assign]
    asyncio.run(
        service.retrieve_for_effort(
            (
                "Trong tình huống người lao động từ chối công việc nguy hiểm, "
                "doanh nghiệp phải xử lý thế nào và có phải bồi thường không?"
            ),
            "instant",
        )
    )

    assert routes == ["single_hop"]
    assert len(store.calls) == 1
    assert store.calls[0][1] == 5


def test_high_keeps_complex_question_on_graph_route() -> None:
    class _Store:
        def retrieve(self, _: str, __: int) -> list[dict[str, object]]:
            return []

    service = RetrievalService(
        SimpleNamespace(
            retriever_backend="hybrid_rag",
            retrieval_top_k=10,
        )
    )
    routes: list[str] = []

    async def get_store(route: str = "single_hop") -> _Store:
        routes.append(route)
        return _Store()

    service._get_store = get_store  # type: ignore[method-assign]
    asyncio.run(
        service.retrieve_for_effort(
            (
                "Trong tình huống người lao động từ chối công việc nguy hiểm, "
                "doanh nghiệp phải xử lý thế nào và có phải bồi thường không?"
            ),
            "high",
        )
    )

    assert routes == ["multi_hop"]


def test_instant_chat_skips_rewrite_and_summary_refresh() -> None:
    class _Db:
        def __init__(self) -> None:
            self.added: list[object] = []

        def add(self, value: object) -> None:
            self.added.append(value)

        async def flush(self) -> None:
            conversation = next(
                (
                    value
                    for value in self.added
                    if isinstance(value, Conversation)
                ),
                None,
            )
            if conversation is not None and conversation.id is None:
                conversation.id = uuid.uuid4()

        async def execute(self, *_: object, **__: object) -> None:
            return None

        async def scalar(self, *_: object, **__: object) -> int:
            return 0

        async def commit(self) -> None:
            return None

        async def rollback(self) -> None:
            return None

        async def refresh(self, value: object) -> None:
            if isinstance(value, ChatMessage) and value.id is None:
                value.id = uuid.uuid4()

    class _Retrieval:
        def __init__(self) -> None:
            self.efforts: list[str] = []

        async def retrieve_for_effort(
            self,
            _: str,
            effort: str,
        ) -> list[dict[str, object]]:
            self.efforts.append(effort)
            return []

    class _Freshness:
        async def verify_sources(self, _: object) -> object:
            raise AssertionError("Freshness must not run without sources")

    class _Cache:
        @staticmethod
        def eligible(*_: object, **__: object) -> bool:
            return False

    retrieval = _Retrieval()
    memory = SimpleNamespace(refresh=AsyncMock())
    ai = SimpleNamespace(complete=AsyncMock(), complete_json=AsyncMock())
    result = asyncio.run(
        chat(
            ChatRequest(
                message="Thời hạn thử việc là bao lâu?",
                effort="instant",
            ),
            db=_Db(),
            user=SimpleNamespace(id=uuid.uuid4(), preferred_name="An"),
            settings=Settings(
                _env_file=None,
                session_secret="effort-test-secret",
            ),
            retrieval=retrieval,
            freshness=_Freshness(),
            ai=ai,
            memory=memory,
            answer_cache=_Cache(),
        )
    )

    assert result.effort == "instant"
    assert retrieval.efforts == ["instant"]
    ai.complete.assert_not_awaited()
    ai.complete_json.assert_not_awaited()
    memory.refresh.assert_not_awaited()
