from __future__ import annotations

import os

from celery import Celery


redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
broker_url = os.getenv("CELERY_BROKER_URL", redis_url.replace("/0", "/1"))
result_backend = os.getenv("CELERY_RESULT_BACKEND")
if result_backend is None and broker_url.startswith(("redis://", "rediss://")):
    result_backend = redis_url.replace("/0", "/2")
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
        "verify-legal-corpus-every-night": {
            "task": "vlegal.verify_legal_corpus",
            "schedule": 24 * 60 * 60,
        }
    },
)
