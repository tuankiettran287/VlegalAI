# syntax=docker/dockerfile:1.7

ARG NODE_VERSION=22
ARG PYTHON_VERSION=3.13

FROM node:${NODE_VERSION}-alpine AS frontend

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --include=dev --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


FROM python:${PYTHON_VERSION}-slim-bookworm AS python-builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /build

RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --upgrade pip setuptools wheel \
    && /opt/venv/bin/python -m pip install --requirement requirements.txt \
    && find /opt/venv -type d -name __pycache__ -prune -exec rm -rf '{}' +


FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ARG APP_UID=10001
ARG APP_GID=10001
ARG VCS_REF=""
ARG BUILD_DATE=""

LABEL org.opencontainers.image.title="VLegal AI" \
      org.opencontainers.image.description="Unified React, FastAPI, worker and GraphRAG runtime" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    WEB_CONCURRENCY=1 \
    FRONTEND_DIST_DIR=/app/frontend-dist \
    HOME=/home/vlegal

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid "${APP_GID}" vlegal \
    && useradd \
       --uid "${APP_UID}" \
       --gid "${APP_GID}" \
       --create-home \
       --shell /usr/sbin/nologin \
       vlegal \
    && mkdir -p /app/legal-data /app/storage/graphrag /app/frontend-dist \
    && chown -R vlegal:vlegal /app /home/vlegal

COPY --from=python-builder /opt/venv /opt/venv
COPY --chown=vlegal:vlegal app ./app
COPY --chown=vlegal:vlegal migrations ./migrations
COPY --chown=vlegal:vlegal alembic.ini ./
COPY --chown=vlegal:vlegal scripts/*.py ./scripts/
COPY --chown=vlegal:vlegal docker/gunicorn.conf.py ./docker/gunicorn.conf.py
COPY --chown=vlegal:vlegal --from=frontend /build/dist ./frontend-dist

USER vlegal

EXPOSE 8080
STOPSIGNAL SIGTERM

# Cloud Run Jobs and Worker Pools override this command while reusing the
# exact same commit image as the public web service.
CMD ["gunicorn", "--config", "/app/docker/gunicorn.conf.py", "app.main:app"]
