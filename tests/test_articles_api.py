from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from app.api import get_article


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
