from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from celery import Celery
from celery.schedules import crontab
from sqlalchemy import select

from app.core.celery import postgres_celery_urls
from app.core.config import get_settings
from app.db import SessionFactory
from app.models import Article, LegalDocument
from app.services.ai import GeminiService
from app.services.articles import ArticleResearchService
from app.services.freshness import LegalFreshnessService
from app.services.google_search import GoogleSearchService
from app.services.indexer import LegalIndexer
from app.services.tavily import TavilyService

logger = logging.getLogger(__name__)
settings = get_settings()
ARTICLE_TIMEZONE = ZoneInfo("Asia/Bangkok")
ARTICLE_PUBLISH_HOURS = (7, 12, 15, 18, 22)
ARTICLE_BATCH_SIZE = 10
broker_url, result_backend = postgres_celery_urls(settings.database_url)
celery_app = Celery(
    "vlegal",
    broker=broker_url,
    backend=result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_ignore_result=result_backend is None,
    timezone="Asia/Bangkok",
    beat_schedule={
        "verify-legal-corpus-every-night": {
            "task": "vlegal.verify_legal_corpus",
            "schedule": 24 * 60 * 60,
        },
        "publish-legal-articles-five-times-daily": {
            "task": "vlegal.publish_daily_legal_article",
            "schedule": crontab(
                hour=",".join(str(hour) for hour in ARTICLE_PUBLISH_HOURS),
                minute=0,
            ),
        }
    },
)


async def _verify_corpus() -> dict[str, int]:
    ai = GeminiService(settings)
    try:
        tavily = TavilyService(settings)
        google_search = GoogleSearchService(settings, ai)
        freshness = LegalFreshnessService(
            settings,
            ai,
            tavily,
            google_search,
            LegalIndexer(settings),
        )
        async with SessionFactory() as db:
            documents = (
                await db.scalars(
                    select(LegalDocument).order_by(
                        LegalDocument.verified_at.asc().nullsfirst()
                    )
                )
            ).all()
        checked = updated = failed = 0
        for document in documents:
            try:
                _, changed = await freshness.verify_sources(
                    [{
                        "doc_id": document.external_doc_id,
                        "title": document.title,
                        "citation": f"{document.code} {document.title}",
                    }]
                )
                checked += 1
                updated += int(changed)
            except Exception:
                failed += 1
                logger.exception(
                    "Legal freshness verification failed for document_id=%s",
                    document.id,
                )
    finally:
        await ai.close()
    return {"checked": checked, "updated": updated, "failed": failed}


@celery_app.task(name="vlegal.verify_legal_corpus")
def verify_legal_corpus() -> dict[str, int]:
    return asyncio.run(_verify_corpus())


def _article_excerpt(value: str) -> str:
    plain = re.sub(r"\[W\d+\]", "", value)
    plain = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", plain)
    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", plain)
    plain = re.sub(r"[*_`#>-]+", " ", plain)
    plain = re.sub(r"\s+", " ", plain).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", plain)[:500]


def _article_source_title(
    value: str,
    source_url: str | None,
    *,
    fallback: str,
) -> str:
    title = re.sub(r"\s+", " ", value or "").strip()[:500]
    normalized = title.casefold().removeprefix("www.")
    generic_titles = {
        "",
        "web source",
        "google search source",
        "nguồn web",
        "nguồn google search",
    }
    try:
        hostname = (
            (urlparse(source_url or "").hostname or "")
            .casefold()
            .removeprefix("www.")
        )
    except ValueError:
        hostname = ""
    is_domain_title = bool(
        hostname
        and normalized
        and (
            hostname == normalized
            or hostname.endswith(f".{normalized}")
            or normalized.endswith(f".{hostname}")
        )
    )
    if normalized in generic_titles or is_domain_title:
        return fallback
    return title or fallback


def _article_card_excerpt(
    summary: str,
    source_excerpt: str,
    *,
    topic: str,
    source_title: str,
) -> str:
    summary_excerpt = _article_excerpt(summary)
    unavailable_markers = (
        "vlegal chưa thể hoàn tất phần diễn giải tự động",
        "ai tạm thời không khả dụng",
        "kết quả tìm kiếm có dẫn nguồn",
    )
    if summary_excerpt and not any(
        marker in summary_excerpt.casefold()
        for marker in unavailable_markers
    ):
        return summary_excerpt

    source_excerpt_clean = _article_excerpt(source_excerpt)
    source_looks_noisy = (
        source_excerpt.count("](") > 3
        or source_excerpt.count("![") > 1
    )
    if len(source_excerpt_clean) >= 80 and not source_looks_noisy:
        return source_excerpt_clean

    return (
        f"Tổng hợp cập nhật pháp lý mới nhất về {topic}, dựa trên nguồn "
        f"công khai “{source_title}”. Mở bài viết gốc để xem toàn bộ nội dung "
        "và đối chiếu thông tin."
    )[:500]


def _article_content_needs_refresh(value: str) -> bool:
    normalized = (value or "").casefold()
    return any(
        marker in normalized
        for marker in (
            "vlegal chưa thể hoàn tất phần diễn giải tự động",
            "ai tạm thời không khả dụng",
            "## kết quả tìm kiếm có dẫn nguồn",
        )
    )


def _article_publication_slot(value: datetime) -> tuple[date, int, int]:
    checked_at = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    local_time = checked_at.astimezone(ARTICLE_TIMEZONE)
    eligible_hours = [
        (index, hour)
        for index, hour in enumerate(ARTICLE_PUBLISH_HOURS)
        if hour <= local_time.hour
    ]
    if eligible_hours:
        slot_index, slot_hour = eligible_hours[-1]
        return local_time.date(), slot_hour, slot_index
    return (
        local_time.date() - timedelta(days=1),
        ARTICLE_PUBLISH_HOURS[-1],
        len(ARTICLE_PUBLISH_HOURS) - 1,
    )


async def _publish_daily_article(now: datetime | None = None) -> dict[str, Any]:
    if not settings.daily_article_enabled:
        return {"published": False, "reason": "disabled"}
    topics = [topic.strip() for topic in settings.daily_article_topics if topic.strip()]
    if not topics:
        return {"published": False, "reason": "no_topics"}

    checked_at = now or datetime.now(UTC)
    slot_date, slot_hour, slot_index = _article_publication_slot(checked_at)
    slot_label = f"{slot_hour:02d}:00"
    batch_position = (
        slot_date.toordinal() * len(ARTICLE_PUBLISH_HOURS) + slot_index
    ) * ARTICLE_BATCH_SIZE
    batch = [
        {
            "number": number + 1,
            "topic": topics[(batch_position + number) % len(topics)],
            "slug": (
                f"cap-nhat-phap-ly-{slot_date.isoformat()}-"
                f"{slot_hour:02d}00-{number + 1:02d}"
            ),
        }
        for number in range(ARTICLE_BATCH_SIZE)
    ]
    pending: list[dict[str, Any]] = []
    skipped_ids: list[str] = []
    for item in batch:
        needs_refresh = False
        async with SessionFactory() as db:
            existing = await db.scalar(
                select(Article).where(Article.slug == item["slug"])
            )
            if isinstance(existing, Article):
                needs_refresh = _article_content_needs_refresh(existing.content)
                if not needs_refresh:
                    repaired_title = _article_source_title(
                        existing.title,
                        existing.source_url,
                        fallback=f"Cập nhật pháp lý: {item['topic']}",
                    )
                    existing_sources = (
                        existing.web_sources
                        if isinstance(existing.web_sources, list)
                        else []
                    )
                    existing_primary = (
                        existing_sources[0]
                        if existing_sources
                        and isinstance(existing_sources[0], dict)
                        else {}
                    )
                    repaired_excerpt = _article_card_excerpt(
                        existing.content,
                        str(existing_primary.get("excerpt") or ""),
                        topic=str(item["topic"]),
                        source_title=repaired_title,
                    )
                    if (
                        repaired_title != existing.title
                        or (
                            repaired_excerpt
                            and repaired_excerpt != existing.excerpt
                        )
                    ):
                        existing.title = repaired_title
                        if repaired_excerpt:
                            existing.excerpt = repaired_excerpt
                        await db.commit()
        if existing is None or needs_refresh:
            pending.append(item)
        else:
            skipped_ids.append(str(getattr(existing, "id", existing)))

    if not pending:
        return {
            "published": False,
            "reason": "already_published",
            "published_count": 0,
            "skipped_count": len(batch),
            "slot": slot_label,
            "article_ids": skipped_ids,
            "slugs": [str(item["slug"]) for item in batch],
        }

    published_ids: list[str] = []
    refreshed_ids: list[str] = []
    failures: list[str] = []
    ai = GeminiService(settings)
    try:
        tavily = TavilyService(settings)
        google_search = GoogleSearchService(settings, ai)
        research = ArticleResearchService(tavily, google_search, ai)
        for item in pending:
            topic = str(item["topic"])
            slug = str(item["slug"])
            try:
                result = await research.search(
                    f"{topic}; bản tin số {item['number']} lúc {slot_label} "
                    f"ngày {slot_date:%d/%m/%Y}; cập nhật quy định, chính sách "
                    "và vấn đề thực tiễn mới nhất"
                )
                sources = (
                    result.get("sources")
                    if isinstance(result.get("sources"), list)
                    else []
                )
                summary = str(result.get("summary") or "").strip()
                if not summary:
                    raise RuntimeError("Article research returned empty content")
                primary_source = (
                    sources[0]
                    if sources and isinstance(sources[0], dict)
                    else {}
                )
                source_url = str(primary_source.get("url") or "").strip() or None
                source_title = re.sub(
                    r"\s+",
                    " ",
                    str(primary_source.get("title") or "").strip(),
                )[:500]
                article_title = _article_source_title(
                    source_title,
                    source_url,
                    fallback=f"Cập nhật pháp lý: {topic}",
                )
                async with SessionFactory() as db:
                    existing_article = await db.scalar(
                        select(Article).where(Article.slug == slug)
                    )
                    article_excerpt = _article_card_excerpt(
                        summary,
                        str(primary_source.get("excerpt") or ""),
                        topic=topic,
                        source_title=article_title,
                    )
                    if isinstance(existing_article, Article):
                        if not _article_content_needs_refresh(
                            existing_article.content
                        ):
                            skipped_ids.append(str(existing_article.id))
                            continue
                        article = existing_article
                        article.title = article_title
                        article.excerpt = article_excerpt
                        article.content = summary
                        article.category = "Cập nhật pháp luật"
                        article.status = "PUBLISHED"
                        article.source_url = source_url
                        article.web_sources = sources
                    else:
                        article = Article(
                            author_id=None,
                            slug=slug,
                            title=article_title,
                            excerpt=article_excerpt,
                            content=summary,
                            category="Cập nhật pháp luật",
                            status="PUBLISHED",
                            source_url=source_url,
                            web_sources=sources,
                            published_at=checked_at,
                        )
                        db.add(article)
                    await db.commit()
                    await db.refresh(article)
                if isinstance(existing_article, Article):
                    refreshed_ids.append(str(article.id))
                else:
                    published_ids.append(str(article.id))
                logger.info(
                    "Saved scheduled legal article article_id=%s "
                    "slot=%s item=%s topic=%s refreshed=%s",
                    article.id,
                    slot_label,
                    item["number"],
                    topic,
                    isinstance(existing_article, Article),
                )
            except Exception as exc:
                failures.append(slug)
                logger.exception(
                    "Scheduled legal article failed slot=%s item=%s "
                    "topic=%s error_type=%s",
                    slot_label,
                    item["number"],
                    topic,
                    type(exc).__name__,
                )
    finally:
        await ai.close()

    if failures:
        raise RuntimeError(
            f"{len(failures)} of {len(batch)} scheduled articles failed "
            f"for slot {slot_date.isoformat()} {slot_label}: {', '.join(failures)}"
        )

    return {
        "published": bool(published_ids or refreshed_ids),
        "published_count": len(published_ids),
        "refreshed_count": len(refreshed_ids),
        "skipped_count": len(skipped_ids),
        "slot": slot_label,
        "article_ids": [*skipped_ids, *published_ids, *refreshed_ids],
        "slugs": [str(item["slug"]) for item in batch],
    }


@celery_app.task(
    bind=True,
    name="vlegal.publish_daily_legal_article",
    max_retries=3,
)
def publish_daily_legal_article(task: object) -> dict[str, Any]:
    try:
        return asyncio.run(_publish_daily_article())
    except Exception as exc:
        logger.exception("Daily legal article publication failed")
        retry = getattr(task, "retry")
        raise retry(exc=exc, countdown=30 * 60)
