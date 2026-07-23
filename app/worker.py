from __future__ import annotations

import asyncio

from celery import Celery
from sqlalchemy import select

from app.core.celery import postgres_celery_urls
from app.core.config import get_settings
from app.db import SessionFactory
from app.models import LegalDocument
from app.services.ai import QwenService
from app.services.freshness import LegalFreshnessService
from app.services.indexer import LegalIndexer
from app.services.tavily import TavilyService


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
        }
    },
)


async def _verify_corpus() -> dict[str, int]:
    ai = QwenService(settings)
    tavily = TavilyService(settings)
    freshness = LegalFreshnessService(settings, ai, tavily, LegalIndexer(settings))
    async with SessionFactory() as db:
        documents = (
            await db.scalars(select(LegalDocument).order_by(LegalDocument.verified_at.asc().nullsfirst()))
        ).all()
    checked = updated = failed = 0
    try:
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
    finally:
        await ai.close()
    return {"checked": checked, "updated": updated, "failed": failed}


@celery_app.task(name="vlegal.verify_legal_corpus")
def verify_legal_corpus() -> dict[str, int]:
    return asyncio.run(_verify_corpus())
