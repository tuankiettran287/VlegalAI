# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS app-python-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false
WORKDIR /app
RUN groupadd --system vlegal && useradd --system --gid vlegal --create-home vlegal
COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./
RUN mkdir -p /app/storage && chown -R vlegal:vlegal /app

FROM app-python-base AS api
ENV PORT=8000 WEB_CONCURRENCY=1
USER vlegal
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/api/health/live', timeout=3)"
CMD ["sh", "-c", "exec gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY} --bind 0.0.0.0:${PORT} --timeout 120 --graceful-timeout 30 --keep-alive 5 --max-requests 2000 --max-requests-jitter 200"]

FROM app-python-base AS worker
USER vlegal
HEALTHCHECK NONE
CMD ["celery", "-A", "app.worker.celery_app", "worker", "--loglevel=INFO", "--concurrency=1"]

FROM python:3.12-slim AS beat
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.beat.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.beat.txt
COPY app/__init__.py ./app/__init__.py
COPY app/core/__init__.py ./app/core/__init__.py
COPY app/core/celery.py ./app/core/celery.py
COPY app/scheduler.py ./app/scheduler.py
HEALTHCHECK NONE
CMD ["celery", "-A", "app.scheduler.celery_app", "beat", "--loglevel=INFO"]

FROM python:3.12-slim AS migrate
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.migrate.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.migrate.txt
COPY app/__init__.py ./app/__init__.py
COPY app/core ./app/core
COPY app/models.py ./app/models.py
COPY migrations ./migrations
COPY alembic.ini ./
HEALTHCHECK NONE
CMD ["alembic", "upgrade", "head"]

FROM python:3.12-slim AS model-init
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.model-init.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.model-init.txt
COPY scripts/download_qwen_model.py ./scripts/download_qwen_model.py
COPY scripts/download_embedding_model.py ./scripts/download_embedding_model.py
HEALTHCHECK NONE
CMD ["sh", "-c", "python scripts/download_qwen_model.py --output-dir /models/qwen3 && python scripts/download_embedding_model.py --output-dir /models/embedding"]

FROM node:22-alpine AS frontend-builder
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine AS frontend
ENV PORT=8080 API_UPSTREAM=http://api:8000
COPY docker/frontend.conf.template /etc/nginx/templates/default.conf.template
COPY --from=frontend-builder /src/frontend/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget --spider -q "http://127.0.0.1:${PORT}/healthz"

# Keep `docker build .` backward compatible; Compose/CI use explicit targets.
FROM api AS default
