# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    TOKENIZERS_PARALLELISM=false \
    EMBEDDING_MODEL_PATH=/models/embedding \
    LEGAL_DATA_DIR=/app/legal-data \
    LEGAL_STORAGE_DIR=/app/storage/graphrag \
    LEGAL_GRAPHRAG_DB=/app/storage/graphrag/legal_graphrag.sqlite

WORKDIR /app

RUN groupadd --gid 10001 vlegal \
    && useradd --uid 10001 --gid vlegal --create-home --shell /usr/sbin/nologin vlegal

COPY requirements.reindex.txt ./
RUN pip install -r requirements.reindex.txt

COPY app ./app
COPY scripts/sync_external_graphrag.py ./scripts/sync_external_graphrag.py

RUN mkdir -p /app/storage/graphrag /app/legal-data \
    && chown -R vlegal:vlegal /app

USER vlegal
HEALTHCHECK NONE

ENTRYPOINT ["python", "scripts/sync_external_graphrag.py"]
