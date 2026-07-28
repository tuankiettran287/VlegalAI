from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace


def test_daily_article_publisher_is_idempotent_and_publishes_research(
    monkeypatch,
) -> None:
    from app import worker

    added: list[object] = []

    class _Session:
        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def scalar(self, _: object) -> object:
            return None

        def add(self, value: object) -> None:
            added.append(value)

        async def commit(self) -> None:
            return None

        async def refresh(self, value: object) -> None:
            value.id = uuid.uuid4()

    sessions = [_Session(), _Session()]
    monkeypatch.setattr(worker, "SessionFactory", lambda: sessions.pop(0))
    monkeypatch.setattr(
        worker,
        "settings",
        SimpleNamespace(
            daily_article_enabled=True,
            daily_article_topics=["chủ đề kiểm thử"],
        ),
    )

    class _Ai:
        def __init__(self, _: object) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class _Research:
        def __init__(self, *_: object) -> None:
            return None

        async def search(self, query: str) -> dict[str, object]:
            assert "chủ đề kiểm thử" in query
            return {
                "summary": "Nội dung cập nhật có căn cứ rõ ràng [W1].",
                "sources": [{
                    "id": "W1",
                    "title": "Nguồn kiểm thử",
                    "url": "https://example.com/legal-update",
                }],
            }

    monkeypatch.setattr(worker, "GeminiService", _Ai)
    monkeypatch.setattr(worker, "TavilyService", lambda _: object())
    monkeypatch.setattr(worker, "GoogleSearchService", lambda *_: object())
    monkeypatch.setattr(worker, "ArticleResearchService", _Research)

    result = asyncio.run(
        worker._publish_daily_article(datetime(2026, 7, 29, 1, tzinfo=UTC))
    )
    assert result["published"] is True
    assert result["slug"] == "cap-nhat-phap-ly-2026-07-29"
    assert len(added) == 1
    article = added[0]
    assert article.status == "PUBLISHED"
    assert article.category == "Cập nhật pháp luật"
    assert article.web_sources[0]["id"] == "W1"


def test_daily_article_publisher_skips_when_disabled(monkeypatch) -> None:
    from app import worker

    monkeypatch.setattr(
        worker,
        "settings",
        SimpleNamespace(daily_article_enabled=False, daily_article_topics=[]),
    )
    result = asyncio.run(worker._publish_daily_article())
    assert result == {"published": False, "reason": "disabled"}
