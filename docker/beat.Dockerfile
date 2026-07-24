# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 vlegal \
    && useradd --uid 10001 --gid vlegal --create-home --shell /usr/sbin/nologin vlegal

COPY requirements.beat.txt ./
RUN pip install --no-cache-dir -r requirements.beat.txt

COPY --chown=vlegal:vlegal app/__init__.py ./app/__init__.py
COPY --chown=vlegal:vlegal app/core/__init__.py ./app/core/__init__.py
COPY --chown=vlegal:vlegal app/core/celery.py ./app/core/celery.py
COPY --chown=vlegal:vlegal app/scheduler.py ./app/scheduler.py

USER vlegal

HEALTHCHECK NONE

CMD ["sh", "-c", "exec celery -A app.scheduler.celery_app beat --loglevel=\"${LOG_LEVEL:-INFO}\""]
