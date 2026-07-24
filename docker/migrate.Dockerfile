# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 vlegal \
    && useradd --uid 10001 --gid vlegal --create-home --shell /usr/sbin/nologin vlegal

COPY requirements.migrate.txt ./
RUN pip install --no-cache-dir -r requirements.migrate.txt

COPY --chown=vlegal:vlegal app/__init__.py ./app/__init__.py
COPY --chown=vlegal:vlegal app/core ./app/core
COPY --chown=vlegal:vlegal app/models.py ./app/models.py
COPY --chown=vlegal:vlegal migrations ./migrations
COPY --chown=vlegal:vlegal alembic.ini ./

USER vlegal

HEALTHCHECK NONE

CMD ["alembic", "upgrade", "head"]
