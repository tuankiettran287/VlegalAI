from __future__ import annotations

import asyncio
import logging
import re
from types import SimpleNamespace

import pytest
from fastapi import Request, Response

from app import main


def test_request_id_accepts_only_log_and_header_safe_values() -> None:
    assert main._normalized_request_id("client.request-_42") == "client.request-_42"

    for unsafe in (
        "",
        "request id with spaces",
        "request\r\nforged-header: yes",
        "x" * 65,
        "unicode-đ",
    ):
        generated = main._normalized_request_id(unsafe)
        assert generated != unsafe
        assert re.fullmatch(r"[0-9a-f]{32}", generated)


def test_mutating_request_is_logged_before_and_after_processing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/chat",
        "raw_path": b"/api/chat",
        "query_string": b"",
        "headers": [(b"x-request-id", b"request-42")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 443),
        "app": SimpleNamespace(
            state=SimpleNamespace(request_slots=asyncio.Semaphore(1))
        ),
    }

    async def scenario() -> Response:
        request = Request(scope)

        async def call_next(_: Request) -> Response:
            return Response(status_code=200)

        return await main.request_context(request, call_next)

    with caplog.at_level(logging.INFO, logger="app.main"):
        response = asyncio.run(scenario())

    assert response.headers["X-Request-ID"] == "request-42"
    assert "stage=received request_id=request-42" in caplog.text
    assert "stage=completed request_id=request-42" in caplog.text


def _patch_lifespan_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    retrieval_close_error: Exception | None = None,
    startup_error: Exception | None = None,
) -> None:
    class _AI:
        async def close(self) -> None:
            events.append("ai.close")

    class _Retrieval:
        async def close(self) -> None:
            events.append("retrieval.close")
            if retrieval_close_error:
                raise retrieval_close_error

    monkeypatch.setattr(main, "GeminiService", lambda _: _AI())
    monkeypatch.setattr(main, "TavilyService", lambda _: SimpleNamespace())
    monkeypatch.setattr(
        main,
        "GoogleSearchService",
        lambda *_: SimpleNamespace(),
    )
    monkeypatch.setattr(main, "LegalIndexer", lambda _: SimpleNamespace())
    monkeypatch.setattr(main, "RetrievalService", lambda _: _Retrieval())

    def freshness_factory(*_: object) -> object:
        if startup_error:
            raise startup_error
        return SimpleNamespace()

    monkeypatch.setattr(main, "LegalFreshnessService", freshness_factory)
    monkeypatch.setattr(main, "GuestRateLimiter", lambda _: SimpleNamespace())
    monkeypatch.setattr(
        main,
        "ConversationMemoryService",
        lambda *_: SimpleNamespace(),
    )
    monkeypatch.setattr(
        main,
        "SemanticAnswerCacheService",
        lambda *_: SimpleNamespace(),
    )
    monkeypatch.setattr(
        main,
        "ArticleResearchService",
        lambda *_: SimpleNamespace(),
    )


def test_lifespan_closes_retrieval_before_ai_on_normal_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _patch_lifespan_dependencies(monkeypatch, events)

    async def scenario() -> None:
        async with main.lifespan(SimpleNamespace(state=SimpleNamespace())):
            events.append("yield")

    asyncio.run(scenario())

    assert events == ["yield", "retrieval.close", "ai.close"]


def test_lifespan_closes_ai_even_when_retrieval_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _patch_lifespan_dependencies(
        monkeypatch,
        events,
        retrieval_close_error=RuntimeError("retrieval cleanup failed"),
    )

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="retrieval cleanup failed"):
            async with main.lifespan(SimpleNamespace(state=SimpleNamespace())):
                pass

    asyncio.run(scenario())

    assert events == ["retrieval.close", "ai.close"]


def test_lifespan_cleans_partial_startup_when_later_constructor_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    _patch_lifespan_dependencies(
        monkeypatch,
        events,
        startup_error=RuntimeError("freshness startup failed"),
    )

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="freshness startup failed"):
            async with main.lifespan(SimpleNamespace(state=SimpleNamespace())):
                raise AssertionError("lifespan must not yield")

    asyncio.run(scenario())

    assert events == ["retrieval.close", "ai.close"]
