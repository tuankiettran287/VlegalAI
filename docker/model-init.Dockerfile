# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 vlegal \
    && useradd --uid 10001 --gid vlegal --create-home --shell /usr/sbin/nologin vlegal

COPY requirements.model-init.txt ./
RUN pip install -r requirements.model-init.txt

COPY scripts/download_qwen_model.py ./scripts/download_qwen_model.py
COPY scripts/download_embedding_model.py ./scripts/download_embedding_model.py

RUN mkdir -p /models/qwen3 /models/embedding \
    && chown -R vlegal:vlegal /app /models/qwen3 /models/embedding

USER vlegal
HEALTHCHECK NONE

CMD ["sh", "-c", "python scripts/download_qwen_model.py --output-dir /models/qwen3 && python scripts/download_embedding_model.py --output-dir /models/embedding"]
