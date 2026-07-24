# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=0 \
    TRANSFORMERS_OFFLINE=0 \
    EMBEDDING_MODEL_PATH=/models/embedding

WORKDIR /app

RUN groupadd --gid 10001 vlegal \
    && useradd --uid 10001 --gid vlegal --create-home --shell /usr/sbin/nologin vlegal

COPY requirements.model-init.txt ./
RUN pip install --no-cache-dir -r requirements.model-init.txt

COPY --chown=vlegal:vlegal scripts/download_embedding_model.py ./scripts/download_embedding_model.py
RUN mkdir -p /models/embedding \
    && chown -R vlegal:vlegal /models/embedding

USER vlegal

HEALTHCHECK NONE

CMD ["python", "scripts/download_embedding_model.py", "--output-dir", "/models/embedding"]
