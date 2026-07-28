from __future__ import annotations

import hashlib
from array import array
from dataclasses import dataclass
from typing import Iterable

import psycopg
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from app.services.embeddings import EmbeddingConfig


def embedding_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _postgres_dsn(database_url: str) -> str:
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("DATABASE_URL must point to PostgreSQL")
    query = dict(url.query)
    if "ssl" in query and "sslmode" not in query:
        query["sslmode"] = query.pop("ssl")
    return url.set(
        drivername="postgresql",
        query=query,
    ).render_as_string(hide_password=False)


@dataclass(frozen=True)
class EmbeddingCheckpointRecord:
    chunk_id: str
    content_hash: str
    vector: list[float]


class PostgresEmbeddingCheckpoint:
    """Persistent cache that lets a bulk reindex resume after a task restart."""

    def __init__(
        self,
        database_url: str,
        embedding_config: EmbeddingConfig,
    ) -> None:
        if not database_url.strip():
            raise ValueError(
                "DATABASE_URL is required when embedding checkpoints are enabled."
            )
        self._dsn = _postgres_dsn(database_url)
        self._model = embedding_config.model
        self._revision = embedding_config.model_revision
        self._dimensions = embedding_config.dimensions

    def _connect(self):
        return psycopg.connect(
            self._dsn,
            row_factory=dict_row,
            autocommit=True,
        )

    def load(self) -> dict[str, tuple[str, list[float]]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT chunk_id, content_sha256, embedding
                    FROM graphrag_embedding_checkpoint
                    WHERE embedding_model = %s
                      AND embedding_revision = %s
                      AND embedding_dimensions = %s
                    """,
                    (self._model, self._revision, self._dimensions),
                )
                rows = cursor.fetchall()

        cached: dict[str, tuple[str, list[float]]] = {}
        expected_bytes = self._dimensions * array("f").itemsize
        for row in rows:
            blob = bytes(row["embedding"])
            if len(blob) != expected_bytes:
                continue
            values = array("f")
            values.frombytes(blob)
            cached[str(row["chunk_id"])] = (
                str(row["content_sha256"]),
                list(values),
            )
        return cached

    def save(self, records: Iterable[EmbeddingCheckpointRecord]) -> int:
        prepared = [
            {
                "chunk_id": record.chunk_id,
                "content_sha256": record.content_hash,
                "embedding_model": self._model,
                "embedding_revision": self._revision,
                "embedding_dimensions": self._dimensions,
                "embedding": array("f", record.vector).tobytes(),
            }
            for record in records
        ]
        if not prepared:
            return 0

        with self._connect() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO graphrag_embedding_checkpoint (
                            chunk_id,
                            content_sha256,
                            embedding_model,
                            embedding_revision,
                            embedding_dimensions,
                            embedding,
                            updated_at
                        ) VALUES (
                            %(chunk_id)s,
                            %(content_sha256)s,
                            %(embedding_model)s,
                            %(embedding_revision)s,
                            %(embedding_dimensions)s,
                            %(embedding)s,
                            now()
                        )
                        ON CONFLICT (chunk_id) DO UPDATE SET
                            content_sha256 = EXCLUDED.content_sha256,
                            embedding_model = EXCLUDED.embedding_model,
                            embedding_revision = EXCLUDED.embedding_revision,
                            embedding_dimensions = EXCLUDED.embedding_dimensions,
                            embedding = EXCLUDED.embedding,
                            updated_at = now()
                        """,
                        prepared,
                    )
        return len(prepared)
