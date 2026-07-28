from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from celery import Celery
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
        "publish-daily-legal-article": {
            "task": "vlegal.publish_daily_legal_article",
            "schedule": 24 * 60 * 60,
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
    plain = re.sub(r"[*_`#>-]+", " ", plain)
    return re.sub(r"\s+", " ", plain).strip()[:500]


async def _publish_daily_article(now: datetime | None = None) -> dict[str, str | bool]:
    if not settings.daily_article_enabled:
        return {"published": False, "reason": "disabled"}
    topics = [topic.strip() for topic in settings.daily_article_topics if topic.strip()]
    if not topics:
        return {"published": False, "reason": "no_topics"}

    checked_at = now or datetime.now(UTC)
    local_date = checked_at.astimezone(ZoneInfo("Asia/Bangkok")).date()
    slug = f"cap-nhat-phap-ly-{local_date.isoformat()}"
    async with SessionFactory() as db:
        existing_id = await db.scalar(select(Article.id).where(Article.slug == slug))
        if existing_id is not None:
            return {
                "published": False,
                "reason": "already_published",
                "article_id": str(existing_id),
            }

    topic = topics[local_date.toordinal() % len(topics)]
    ai = GeminiService(settings)
    try:
        tavily = TavilyService(settings)
        google_search = GoogleSearchService(settings, ai)
        result = await ArticleResearchService(tavily, google_search, ai).search(
            f"{topic}; cập nhật quy định, chính sách và vấn đề thực tiễn mới nhất"
        )
    finally:
        await ai.close()

    sources = result.get("sources") if isinstance(result.get("sources"), list) else []
    summary = str(result.get("summary") or "").strip()
    if not summary:
        raise RuntimeError("Daily article research returned empty content")
    source_url = (
        str(sources[0].get("url") or "").strip()
        if sources and isinstance(sources[0], dict)
        else None
    )
    async with SessionFactory() as db:
        existing_id = await db.scalar(select(Article.id).where(Article.slug == slug))
        if existing_id is not None:
            return {
                "published": False,
                "reason": "already_published",
                "article_id": str(existing_id),
            }
        article = Article(
            author_id=None,
            slug=slug,
            title=f"Cập nhật pháp lý: {topic}",
            excerpt=_article_excerpt(summary),
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
    logger.info(
        "Published daily legal article article_id=%s topic=%s",
        article.id,
        topic,
    )
    return {
        "published": True,
        "article_id": str(article.id),
        "slug": slug,
    }


@celery_app.task(
    bind=True,
    name="vlegal.publish_daily_legal_article",
    max_retries=3,
)
def publish_daily_legal_article(task: object) -> dict[str, str | bool]:
    try:
        return asyncio.run(_publish_daily_article())
    except Exception as exc:
        logger.exception("Daily legal article publication failed")
        retry = getattr(task, "retry")
        raise retry(exc=exc, countdown=30 * 60)
