FROM node:22-alpine AS frontend-builder
WORKDIR /src/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000 \
    WEB_CONCURRENCY=4
WORKDIR /app
RUN groupadd --system vlegal && useradd --system --gid vlegal --create-home vlegal
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./
COPY --from=frontend-builder /src/frontend/dist ./frontend/dist
RUN mkdir -p /app/storage && chown -R vlegal:vlegal /app
USER vlegal
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=3)"
CMD ["sh", "-c", "gunicorn app.main:app --worker-class uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY} --bind 0.0.0.0:${PORT} --timeout 120 --graceful-timeout 30 --keep-alive 5 --max-requests 2000 --max-requests-jitter 200"]

