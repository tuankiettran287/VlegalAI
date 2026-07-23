# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 vlegal \
    && useradd --uid 10001 --gid vlegal --create-home --shell /usr/sbin/nologin vlegal

COPY requirements.beat.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.beat.txt

COPY app/__init__.py ./app/__init__.py
COPY app/core/__init__.py ./app/core/__init__.py
COPY app/core/celery.py ./app/core/celery.py
COPY app/scheduler.py ./app/scheduler.py

RUN chown -R vlegal:vlegal /app

USER vlegal
HEALTHCHECK NONE

CMD ["celery", "-A", "app.scheduler.celery_app", "beat", "--loglevel=INFO"]
