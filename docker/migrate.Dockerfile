# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 vlegal \
    && useradd --uid 10001 --gid vlegal --create-home --shell /usr/sbin/nologin vlegal

COPY requirements.migrate.txt ./
RUN pip install -r requirements.migrate.txt

COPY app/__init__.py ./app/__init__.py
COPY app/core ./app/core
COPY app/models.py ./app/models.py
COPY migrations ./migrations
COPY alembic.ini ./

RUN chown -R vlegal:vlegal /app

USER vlegal
HEALTHCHECK NONE

CMD ["alembic", "upgrade", "head"]
