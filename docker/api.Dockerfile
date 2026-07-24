# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    PORT=8080 \
    WEB_CONCURRENCY=1

WORKDIR /app

RUN groupadd --gid 10001 vlegal \
    && useradd --uid 10001 --gid vlegal --create-home --shell /usr/sbin/nologin vlegal

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=vlegal:vlegal app ./app
RUN mkdir -p /app/storage \
    && chown vlegal:vlegal /app/storage

USER vlegal

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/api/health/live', timeout=3)"

CMD ["sh", "-c", "exec gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --workers \"$WEB_CONCURRENCY\" --bind \"0.0.0.0:$PORT\" --timeout 3600 --graceful-timeout 30 --keep-alive 5 --max-requests 2000 --max-requests-jitter 200"]
