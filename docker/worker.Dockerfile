# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    CELERY_CONCURRENCY=1

WORKDIR /app

RUN groupadd --gid 10001 vlegal \
    && useradd --uid 10001 --gid vlegal --create-home --shell /usr/sbin/nologin vlegal

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=vlegal:vlegal app ./app
RUN mkdir -p /app/storage \
    && chown vlegal:vlegal /app/storage

USER vlegal

HEALTHCHECK NONE

CMD ["sh", "-c", "exec celery -A app.worker.celery_app worker --loglevel=\"${LOG_LEVEL:-INFO}\" --concurrency=\"$CELERY_CONCURRENCY\""]
