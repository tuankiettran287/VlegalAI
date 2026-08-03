from __future__ import annotations

import asyncio
import threading
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.api import chat
from app.core.config import Settings
from app.models import ChatMessage, Conversation
from app.schemas import ChatRequest
from app.services.ai import GeminiService
from app.services.chat_policy import chat_profile_for_route
from app.services.retrieval import RetrievalService


def test_chat_request_does_not_expose_effort() -> None:
    request = ChatRequest(message="Quyen nghi phep la gi?")

    assert "effort" not in request.model_dump()


def test_automatic_profiles_scale_with_route_complexity() -> None:
    single = chat_profile_for_route("single_hop")
    multi = chat_profile_for_route("multi_hop")
    abstract = chat_profile_for_route("multi_abstract")

    assert single.thinking_budget < multi.thinking_budget < abstract.thinking_budget
    assert single.max_output_tokens < multi.max_output_tokens < abstract.max_output_tokens
    assert single.retrieval_query_limit < multi.retrieval_query_limit


def test_route_profile_controls_vertex_thinking_budget() -> None:
    service = object.__new__(GeminiService)
    service.settings = SimpleNamespace(
        gemini_model="gemini-2.5-flash",
        gemini_thinking_budget=99,
        gemini_thinking_level="low",
    )

    for route, expected_budget in (
        ("single_hop", 0),
        ("multi_hop", 1_024),
        ("multi_abstract", 4_096),
    ):
        payload = service._payload(
            "system",
            "question",
            temperature=0.1,
            max_tokens=500,
            json_schema=None,
            thinking_budget=chat_profile_for_route(route).thinking_budget,
        )
        assert payload["generationConfig"]["thinkingConfig"] == {
            "thinkingBudget": expected_budget,
            "includeThoughts": False,
        }


def test_single_hop_uses_fast_postgres_route() -> None:
    class _Store:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def retrieve(self, query: str, top_k: int) -> list[dict[str, object]]:
            self.calls.append((query, top_k))
            return []

    service = RetrievalService(
        SimpleNamespace(retriever_backend="hybrid_rag", retrieval_top_k=10)
    )
    store = _Store()
    routes: list[str] = []

    async def get_store(route: str = "single_hop") -> _Store:
        routes.append(route)
        return store

    service._get_store = get_store  # type: ignore[method-assign]
    asyncio.run(service.retrieve("Nguoi lao dong co bao nhieu ngay nghi phep?"))

    assert routes == ["single_hop"]
    assert store.calls
    assert all(call[1] == 8 for call in store.calls)


def test_single_hop_runs_planned_queries_concurrently() -> None:
    class _Store:
        def __init__(self) -> None:
            self.active = 0
            self.peak_active = 0
            self.lock = threading.Lock()

        def retrieve(self, _: str, __: int) -> list[dict[str, object]]:
            with self.lock:
                self.active += 1
                self.peak_active = max(self.peak_active, self.active)
            time.sleep(0.05)
            with self.lock:
                self.active -= 1
            return []

    service = RetrievalService(
        SimpleNamespace(retriever_backend="hybrid_rag", retrieval_top_k=10)
    )
    store = _Store()

    async def get_store(_: str = "single_hop") -> _Store:
        return store

    service._get_store = get_store  # type: ignore[method-assign]
    asyncio.run(service.retrieve("Cưỡng bức lao động là gì?"))

    assert store.peak_active >= 2


def test_complex_question_automatically_uses_graph_route() -> None:
    class _Store:
        def retrieve(self, _: str, __: int) -> list[dict[str, object]]:
            return []

    service = RetrievalService(
        SimpleNamespace(retriever_backend="hybrid_rag", retrieval_top_k=10)
    )
    routes: list[str] = []

    async def get_store(route: str = "single_hop") -> _Store:
        routes.append(route)
        return _Store()

    service._get_store = get_store  # type: ignore[method-assign]
    asyncio.run(
        service.retrieve(
            "Trong tinh huong nguoi lao dong tu choi cong viec nguy hiem; "
            "doanh nghiep phai xu ly the nao va co phai boi thuong khong?"
        )
    )

    assert routes == ["multi_hop"]


def test_chat_rewrites_leetspeak_before_single_hop_retrieval() -> None:
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
            self.queries: list[str] = []

        async def retrieve(self, query: str) -> list[dict[str, object]]:
            self.queries.append(query)
            return []

    class _Cache:
        @staticmethod
        def eligible(*_: object, **__: object) -> bool:
            return False

    retrieval = _Retrieval()
    ai = SimpleNamespace(
        complete_json=AsyncMock(
            return_value={
                "rewrite_required": True,
                "rewritten_query": (
                    "Lương cơ bản hiện tại của cán bộ nhà nước là bao nhiêu?"
                ),
                "confidence": 0.98,
                "reason": "Chuẩn hóa teencode.",
            }
        )
    )

    asyncio.run(
        chat(
            ChatRequest(
                message=(
                    "lu0ng c0 b4n hj3n t4j cu4 c4n b0 nk4 nu0c l4 b40 nkj3u?"
                )
            ),
            db=_Db(),
            user=SimpleNamespace(id=uuid.uuid4(), preferred_name="An"),
            settings=Settings(
                _env_file=None,
                session_secret="automatic-routing-test-secret",
            ),
            retrieval=retrieval,
            freshness=SimpleNamespace(),
            ai=ai,
            memory=SimpleNamespace(refresh=AsyncMock()),
            answer_cache=_Cache(),
        )
    )

    assert retrieval.queries == [
        "Lương cơ bản hiện tại của cán bộ nhà nước là bao nhiêu?"
    ]
    ai.complete_json.assert_awaited_once()
