from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

from app.core.celery import postgres_celery_urls
from app.core.schedules import ARTICLE_PUBLISH_HOURS, LEGAL_FRESHNESS_INTERVAL_SECONDS

database_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://vlegal:vlegal@postgres:5432/vlegal",
)
broker_url, result_backend = postgres_celery_urls(database_url)
celery_app = Celery(
    "vlegal-scheduler",
    broker=broker_url,
    backend=result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    task_ignore_result=result_backend is None,
    timezone="Asia/Bangkok",
    beat_schedule={
        "verify-legal-corpus-every-10-days": {
            "task": "vlegal.verify_legal_corpus",
            "schedule": LEGAL_FRESHNESS_INTERVAL_SECONDS,
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
