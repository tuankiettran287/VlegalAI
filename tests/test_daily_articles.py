from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest


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

    monkeypatch.setattr(worker, "SessionFactory", _Session)
    monkeypatch.setattr(worker, "ARTICLE_BATCH_SIZE", 1)
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
            return None

        async def close(self) -> None:
            return None

    class _Research:
        def __init__(self, *_: object) -> None:
            return None

        async def search(self, query: str, **kwargs: object) -> dict[str, object]:
            assert "chủ đề kiểm thử" in query
            assert kwargs["published_on"].isoformat() == "2026-07-29"
            assert kwargs["generate_summary"] is False
            return {
                "summary": "Nội dung cập nhật có căn cứ rõ ràng [W1].",
                "sources": [{
                    "id": "W1",
                    "title": "Nguồn kiểm thử",
                    "url": "https://example.com/legal-update",
                    "excerpt": "Nội dung gốc của bài viết kiểm thử.",
                    "published_date": "2026-07-29T08:30:00+07:00",
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
    assert result["published_count"] == 1
    assert result["slot"] == "07:00"
    assert result["slugs"] == ["cap-nhat-phap-ly-2026-07-29-0700-01"]
    assert len(added) == 1
    article = added[0]
    assert article.status == "PUBLISHED"
    assert article.category == "Tin pháp lý"
    assert article.web_sources[0]["id"] == "W1"
    assert article.title == "Nguồn kiểm thử"
    assert article.excerpt == "Nội dung cập nhật có căn cứ rõ ràng."
    assert article.source_url == "https://example.com/legal-update"
    assert article.published_at.isoformat() == "2026-07-29T01:30:00+00:00"


def test_source_title_rejects_provider_domain() -> None:
    from app.worker import _article_source_title

    assert _article_source_title(
        "luatvietnam.vn",
        "https://luatvietnam.vn/lao-dong/bo-luat-lao-dong.html",
        fallback="Cập nhật pháp lý: pháp luật lao động",
    ) == "Cập nhật pháp lý: pháp luật lao động"
    assert _article_source_title(
        "Quy định mới về hợp đồng lao động",
        "https://example.com/legal-update",
        fallback="fallback",
    ) == "Quy định mới về hợp đồng lao động"


def test_card_excerpt_hides_ai_fallback_and_noisy_navigation() -> None:
    from app.worker import _article_card_excerpt

    excerpt = _article_card_excerpt(
        "VLegal chưa thể hoàn tất phần diễn giải tự động cho chủ đề này.",
        "[Trang chủ](/) [Dịch vụ](/dich-vu) [Đăng nhập](/login) "
        "[Danh mục](/danh-muc) Nội dung trang.",
        topic="pháp luật lao động",
        source_title="Cập nhật Bộ luật Lao động",
    )

    assert "chưa thể hoàn tất" not in excerpt
    assert "Tổng hợp cập nhật pháp lý mới nhất về pháp luật lao động" in excerpt
    assert "Cập nhật Bộ luật Lao động" in excerpt


def test_scheduled_article_batch_publishes_ten_unique_items(monkeypatch) -> None:
    from app import worker

    added: list[object] = []
    searched_topics: list[str] = []

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

    monkeypatch.setattr(worker, "SessionFactory", _Session)
    monkeypatch.setattr(worker, "ARTICLE_BATCH_SIZE", 10)
    monkeypatch.setattr(worker, "ARTICLE_BATCH_DELAY_SECONDS", 0)
    monkeypatch.setattr(
        worker,
        "settings",
        SimpleNamespace(
            daily_article_enabled=True,
            daily_article_topics=[f"chủ đề {index}" for index in range(20)],
        ),
    )

    class _Ai:
        def __init__(self, _: object) -> None:
            return None

        async def close(self) -> None:
            return None

    class _Research:
        def __init__(self, *_: object) -> None:
            return None

        async def search(self, query: str, **_: object) -> dict[str, object]:
            searched_topics.append(query)
            index = len(searched_topics)
            return {
                "summary": f"Phân tích pháp lý cho bản tin số {index} [W1].",
                "sources": [{
                    "id": "W1",
                    "title": f"Tiêu đề nguồn số {index}",
                    "url": f"https://example.com/article-{index}",
                    "excerpt": f"Nội dung nguồn số {index}.",
                    "published_date": "2026-07-29T12:15:00+07:00",
                }],
            }

    monkeypatch.setattr(worker, "GeminiService", _Ai)
    monkeypatch.setattr(worker, "TavilyService", lambda _: object())
    monkeypatch.setattr(worker, "GoogleSearchService", lambda *_: object())
    monkeypatch.setattr(worker, "ArticleResearchService", _Research)

    result = asyncio.run(
        worker._publish_daily_article(datetime(2026, 7, 29, 5, tzinfo=UTC))
    )

    assert result["slot"] == "12:00"
    assert result["published_count"] == 10
    assert result["skipped_count"] == 0
    assert len(result["slugs"]) == 10
    assert len(set(result["slugs"])) == 10
    assert len(added) == 10
    assert len(searched_topics) == 10
    assert len({article.title for article in added}) == 10
    assert all(article.source_url for article in added)


def test_scheduled_article_batch_skips_all_existing_items(monkeypatch) -> None:
    from app import worker

    existing_id = uuid.uuid4()

    class _Session:
        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def scalar(self, _: object) -> object:
            return existing_id

    monkeypatch.setattr(worker, "SessionFactory", _Session)
    monkeypatch.setattr(worker, "ARTICLE_BATCH_SIZE", 10)
    monkeypatch.setattr(
        worker,
        "settings",
        SimpleNamespace(
            daily_article_enabled=True,
            daily_article_topics=[f"chủ đề {index}" for index in range(20)],
        ),
    )

    def _unexpected_ai(_: object) -> object:
        raise AssertionError("AI must not run for an already-published batch")

    monkeypatch.setattr(worker, "GeminiService", _unexpected_ai)

    result = asyncio.run(
        worker._publish_daily_article(datetime(2026, 7, 29, 8, tzinfo=UTC))
    )

    assert result["published"] is False
    assert result["reason"] == "already_published"
    assert result["published_count"] == 0
    assert result["skipped_count"] == 10
    assert len(result["slugs"]) == 10


def test_scheduled_article_refreshes_existing_fallback_content(monkeypatch) -> None:
    from app import worker
    from app.models import Article

    existing = Article(
        id=uuid.uuid4(),
        author_id=None,
        slug="cap-nhat-phap-ly-2026-07-29-0700-01",
        title="example.com",
        excerpt="Nội dung tạm",
        content=(
            "## Kết quả tìm kiếm có dẫn nguồn\n\n"
            "VLegal chưa thể hoàn tất phần diễn giải tự động."
        ),
        category="Cập nhật pháp luật",
        status="PUBLISHED",
        source_url="https://example.com/old",
        web_sources=[],
        published_at=datetime(2026, 7, 29, 0, tzinfo=UTC),
    )
    commits = 0

    class _Session:
        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def scalar(self, _: object) -> object:
            return existing

        def add(self, _: object) -> None:
            raise AssertionError("Refreshing an article must not insert a new row")

        async def commit(self) -> None:
            nonlocal commits
            commits += 1

        async def refresh(self, _: object) -> None:
            return None

    monkeypatch.setattr(worker, "SessionFactory", _Session)
    monkeypatch.setattr(worker, "ARTICLE_BATCH_SIZE", 1)
    monkeypatch.setattr(
        worker,
        "settings",
        SimpleNamespace(
            daily_article_enabled=True,
            daily_article_topics=["pháp luật lao động"],
        ),
    )

    class _Ai:
        def __init__(self, _: object) -> None:
            return None

        async def close(self) -> None:
            return None

    class _Research:
        def __init__(self, *_: object) -> None:
            return None

        async def search(self, _: str, **__: object) -> dict[str, object]:
            return {
                "summary": (
                    "## Nội dung cập nhật\n\n"
                    "Quy định mới có nội dung chi tiết và căn cứ rõ ràng [W1]."
                ),
                "sources": [{
                    "id": "W1",
                    "title": "Quy định mới về pháp luật lao động",
                    "url": "https://example.com/new",
                    "excerpt": "Nội dung nguồn đã được làm sạch.",
                    "published_date": "2026-07-29T07:05:00+07:00",
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
    assert result["published_count"] == 0
    assert result["refreshed_count"] == 1
    assert commits == 1
    assert existing.title == "Quy định mới về pháp luật lao động"
    assert existing.source_url == "https://example.com/new"
    assert "chưa thể hoàn tất" not in existing.content
    assert "Nội dung cập nhật" in existing.content


@pytest.mark.parametrize(
    ("checked_at", "expected_date", "expected_hour"),
    [
        (datetime(2026, 7, 29, 0, tzinfo=UTC), "2026-07-29", 7),
        (datetime(2026, 7, 29, 5, tzinfo=UTC), "2026-07-29", 12),
        (datetime(2026, 7, 29, 8, tzinfo=UTC), "2026-07-29", 15),
        (datetime(2026, 7, 29, 11, tzinfo=UTC), "2026-07-29", 18),
        (datetime(2026, 7, 29, 15, tzinfo=UTC), "2026-07-29", 22),
        (datetime(2026, 7, 28, 23, tzinfo=UTC), "2026-07-28", 22),
    ],
)
def test_article_publication_slot_uses_vietnam_schedule(
    checked_at: datetime,
    expected_date: str,
    expected_hour: int,
) -> None:
    from app.worker import _article_publication_slot

    slot_date, slot_hour, _ = _article_publication_slot(checked_at)

    assert slot_date.isoformat() == expected_date
    assert slot_hour == expected_hour


def test_worker_and_beat_use_five_daily_publication_times() -> None:
    from app import scheduler, worker

    key = "publish-legal-articles-five-times-daily"
    worker_schedule = worker.celery_app.conf.beat_schedule[key]["schedule"]
    beat_schedule = scheduler.celery_app.conf.beat_schedule[key]["schedule"]

    assert worker_schedule._orig_hour == "7,12,15,18,22"
    assert beat_schedule._orig_hour == "7,12,15,18,22"


@pytest.mark.parametrize(
    ("topic", "title", "expected"),
    [
        (
            "pháp luật lao động",
            "Nghị định mới về tiền lương",
            "Cập nhật pháp luật",
        ),
        (
            "pháp luật lao động",
            "Cách chuẩn bị hồ sơ xin việc",
            "Lao động & việc làm",
        ),
        ("bảo hiểm xã hội", "Hướng dẫn hồ sơ hưu trí", "Bảo hiểm & an sinh"),
        ("sở hữu trí tuệ", "Bảo vệ nhãn hiệu", "Sở hữu trí tuệ"),
        ("pháp luật đất đai", "Thủ tục sang tên nhà ở", "Đất đai & nhà ở"),
        (
            "hợp đồng thương mại",
            "Thông tư bãi bỏ quy định trong lĩnh vực thuế",
            "Thuế & tài chính",
        ),
        (
            "bảo hiểm xã hội",
            "Bảo đảm nhân lực cho Trạm Y tế sau sắp xếp",
            "Y tế & giáo dục",
        ),
    ],
)
def test_article_category_uses_relevant_topic_tags(
    topic: str,
    title: str,
    expected: str,
) -> None:
    from app.worker import _article_category

    assert _article_category(topic, title) == expected


def test_article_purge_targets_only_article_table(monkeypatch) -> None:
    from scripts import publish_daily_article

    statements: list[str] = []
    committed = False

    class _Session:
        async def __aenter__(self) -> "_Session":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def scalar(self, statement: object) -> int:
            statements.append(str(statement))
            return 181

        async def execute(self, statement: object) -> None:
            statements.append(str(statement))

        async def commit(self) -> None:
            nonlocal committed
            committed = True

    monkeypatch.setattr(publish_daily_article, "SessionFactory", _Session)

    count = asyncio.run(publish_daily_article.purge_all_articles())

    assert count == 181
    assert committed is True
    assert any("DELETE FROM article" in statement for statement in statements)
    assert all("legal_document" not in statement for statement in statements)


def test_daily_article_publisher_skips_when_disabled(monkeypatch) -> None:
    from app import worker

    monkeypatch.setattr(
        worker,
        "settings",
        SimpleNamespace(daily_article_enabled=False, daily_article_topics=[]),
    )
    result = asyncio.run(worker._publish_daily_article())
    assert result == {"published": False, "reason": "disabled"}
