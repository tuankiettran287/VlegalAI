# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm

# Worker chạy task refresh kho luật: tải văn bản mới, chunk rồi ghi thẳng vào
# PostgreSQL/pgvector và Neo4j. Không ghi ra đĩa và không đọc corpus .docx, nên
# image chỉ cần mã ứng dụng và checkpoint BGE-M3 mount vào /models/embedding.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    EMBEDDING_MODEL_PATH=/models/embedding \
    CELERY_CONCURRENCY=1

WORKDIR /app

RUN groupadd --gid 10001 vlegal \
    && useradd --uid 10001 --gid vlegal --create-home --shell /usr/sbin/nologin vlegal

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=vlegal:vlegal app ./app

USER vlegal

HEALTHCHECK NONE

CMD ["sh", "-c", "exec celery -A app.worker.celery_app worker --loglevel=\"${LOG_LEVEL:-INFO}\" --concurrency=\"$CELERY_CONCURRENCY\""]
