from __future__ import annotations

import asyncio
from typing import Any

from fastapi.concurrency import run_in_threadpool

from app.core.config import Settings
from app.external_graphrag import (
    ExternalGraphRAGConfig,
    Neo4jGraphRAGStore,
    Neo4jPostgresGraphRAGStore,
    PostgresGraphRAGStore,
)
from app.legal_graphrag import GraphRAGStore
from app.services.embeddings import EmbeddingConfig


def _embedding_config(settings: Settings) -> EmbeddingConfig:
    return EmbeddingConfig(
        model_path=settings.embedding_model_path,
        model_repo=settings.embedding_model_repo,
        model_revision=settings.embedding_model_revision,
        device=settings.embedding_device,
        dimensions=settings.postgres_vector_size,
        batch_size=settings.embedding_batch_size,
        max_sequence_length=settings.embedding_max_sequence_length,
    )


def _external_config(settings: Settings) -> ExternalGraphRAGConfig:
    return ExternalGraphRAGConfig(
        neo4j_uri=settings.neo4j_uri,
        neo4j_user=settings.neo4j_user,
        neo4j_password=settings.neo4j_password,
        neo4j_database=settings.neo4j_database,
        database_url=settings.database_url,
        postgres_vector_size=settings.postgres_vector_size,
        embedding_model_path=settings.embedding_model_path,
        embedding_model_repo=settings.embedding_model_repo,
        embedding_model_revision=settings.embedding_model_revision,
        embedding_device=settings.embedding_device,
        embedding_batch_size=settings.embedding_batch_size,
        embedding_max_sequence_length=settings.embedding_max_sequence_length,
    )


class RetrievalService:
    """One store per worker; blocking vendor SDKs are isolated from the event loop."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._store: Any = None
        self._lock = asyncio.Lock()

    async def _get_store(self) -> Any:
        if self._store is not None:
            return self._store
        async with self._lock:
            if self._store is not None:
                return self._store
            config = _external_config(self.settings)
            backend = self.settings.retriever_backend
            if backend == "hybrid_rag":
                self._store = await run_in_threadpool(Neo4jPostgresGraphRAGStore, config)
            elif backend == "rag":
                self._store = await run_in_threadpool(PostgresGraphRAGStore, config)
            elif backend == "graphrag":
                self._store = await run_in_threadpool(Neo4jGraphRAGStore, config)
            else:
                self._store = await run_in_threadpool(
                    GraphRAGStore,
                    self.settings.legal_graphrag_db,
                    _embedding_config(self.settings),
                )
        return self._store

    async def retrieve(self, query: str, top_k: int | None = None) -> list[dict[str, Any]]:
        store = await self._get_store()
        rows = await run_in_threadpool(store.retrieve, query, top_k or self.settings.retrieval_top_k)
        return [serialize_source(row) for row in rows]

    async def stats(self) -> dict[str, Any]:
        store = await self._get_store()
        return await run_in_threadpool(store.stats)

    async def close(self) -> None:
        if self._store is not None and hasattr(self._store, "close"):
            await run_in_threadpool(self._store.close)

    def invalidate(self) -> None:
        self._store = None


def serialize_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": str(source.get("source_id", "")),
        "score": round(float(source.get("score", 0) or 0), 4),
        "chunk_type": str(source.get("chunk_type", "")),
        "citation": str(source.get("citation") or source.get("title") or "Nguồn pháp lý")[:500],
        "title": str(source.get("title") or "")[:500],
        "text": str(source.get("text") or "")[:5000],
        "reasons": [str(item) for item in source.get("reasons", [])],
        "doc_id": str(source.get("doc_id")) if source.get("doc_id") else None,
        "node_id": str(source.get("node_id")) if source.get("node_id") else None,
        "source_url": source.get("source_url"),
    }


def build_context(sources: list[dict[str, Any]], max_chars: int = 24000) -> str:
    blocks: list[str] = []
    size = 0
    for source in sources:
        block = f"[{source['source_id']}] {source['citation']}\n{source['text']}"
        if size + len(block) > max_chars:
            break
        blocks.append(block)
        size += len(block)
    return "\n\n".join(blocks)
