from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from app.api import get_article, list_articles


class _ArticleDb:
    def __init__(self, article: SimpleNamespace) -> None:
        self.article = article
        self.committed = False
        self.refreshed: SimpleNamespace | None = None

    async def scalar(self, _statement: object) -> SimpleNamespace:
        return self.article

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, article: SimpleNamespace) -> None:
        self.refreshed = article


class _ScalarRows:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self.rows


class _ArticleListDb:
    def __init__(self, rows: list[SimpleNamespace], total: int) -> None:
        self.rows = rows
        self.total = total

    async def scalar(self, _statement: object) -> int:
        return self.total

    async def scalars(self, _statement: object) -> _ScalarRows:
        return _ScalarRows(self.rows)


def test_get_article_refreshes_after_commit_before_serializing() -> None:
    now = datetime.now(UTC)
    article = SimpleNamespace(
        id="article-id",
        slug="bai-viet-kiem-thu",
        title="Bài viết kiểm thử",
        excerpt="Tóm tắt",
        content="Nội dung",
        category="Pháp luật",
        status="PUBLISHED",
        source_url=None,
        web_sources=[],
        view_count=3,
        published_at=now,
        created_at=now,
        updated_at=now,
    )
    db = _ArticleDb(article)

    result = asyncio.run(get_article(article.slug, db=db))  # type: ignore[arg-type]

    assert db.committed is True
    assert db.refreshed is article
    assert result["views"] == 4


def test_list_articles_returns_pagination_metadata() -> None:
    now = datetime.now(UTC)
    rows = [
        SimpleNamespace(
            id=f"article-{index}",
            slug=f"bai-viet-{index}",
            title=f"Bài viết {index}",
            excerpt=f"Tóm tắt {index}",
            content=f"Nội dung {index}",
            category="Pháp luật",
            status="PUBLISHED",
            source_url=f"https://example.com/{index}",
            web_sources=[],
            view_count=index,
            published_at=now,
            created_at=now,
            updated_at=now,
        )
        for index in range(3)
    ]
    db = _ArticleListDb(rows, total=53)

    result = asyncio.run(
        list_articles(
            q="",
            limit=30,
            offset=30,
            db=db,  # type: ignore[arg-type]
            user=None,
        )
    )

    assert len(result["items"]) == 3
    assert result["total"] == 53
    assert result["offset"] == 30
    assert result["limit"] == 30
    assert result["has_more"] is True
