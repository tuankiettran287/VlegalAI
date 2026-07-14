from __future__ import annotations

import asyncio
import os

from celery import Celery
from sqlalchemy import select

from app.core.config import get_settings
from app.db import SessionFactory
from app.models import LegalDocument
from app.services.ai import QwenService
from app.services.freshness import LegalFreshnessService
from app.services.indexer import LegalIndexer
from app.services.tavily import TavilyService


settings = get_settings()
celery_app = Celery(
    "vlegal",
    broker=os.getenv("CELERY_BROKER_URL", settings.redis_url.replace("/0", "/1")),
    backend=os.getenv("CELERY_RESULT_BACKEND", settings.redis_url.replace("/0", "/2")),
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
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
        await freshness.close()
    return {"checked": checked, "updated": updated, "failed": failed}


@celery_app.task(name="vlegal.verify_legal_corpus")
def verify_legal_corpus() -> dict[str, int]:
    return asyncio.run(_verify_corpus())
