# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

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
    && /opt/venv/bin/python -m pip install --requirement requirements.txt


FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    WEB_CONCURRENCY=1

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
    && mkdir -p /app/legal-data /app/storage/graphrag \
    && chown -R vlegal:vlegal /app /home/vlegal

COPY --from=builder /opt/venv /opt/venv
COPY --chown=vlegal:vlegal app ./app
COPY --chown=vlegal:vlegal migrations ./migrations
COPY --chown=vlegal:vlegal alembic.ini ./
COPY --chown=vlegal:vlegal scripts/*.py ./scripts/

USER vlegal

EXPOSE 8080
STOPSIGNAL SIGTERM

# API is the default. Cloud Run Jobs/Worker Pools and Compose override this
# command for migrate, reindex, Celery worker and Celery beat.
CMD ["sh", "-c", "exec gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --workers \"${WEB_CONCURRENCY:-1}\" --bind \"0.0.0.0:${PORT:-8080}\" --timeout 3600 --graceful-timeout 30 --keep-alive 5 --max-requests 2000 --max-requests-jitter 200 --worker-tmp-dir /dev/shm --access-logfile - --error-logfile - --capture-output"]
