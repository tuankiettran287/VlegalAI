from __future__ import annotations

from collections import OrderedDict

import pytest

from app.legal_graphrag import (
    LegalGraphBuilder,
    blob_to_vector,
)
from app.services.embedding_checkpoint import (
    EmbeddingCheckpointRecord,
    embedding_content_hash,
)
from app.services.embeddings import EmbeddingConfig


class _Checkpoint:
    def __init__(
        self,
        cached: dict[str, tuple[str, list[float]]],
    ) -> None:
        self.cached = cached
        self.saved: list[EmbeddingCheckpointRecord] = []

    def load(self) -> dict[str, tuple[str, list[float]]]:
        return self.cached

    def save(self, records: list[EmbeddingCheckpointRecord]) -> int:
        self.saved.extend(records)
        return len(records)


class _Embeddings:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(
        self,
        texts: list[str],
        *,
        show_progress: bool = False,
    ) -> list[list[float]]:
        assert show_progress
        self.calls.append(texts)
        return [[0.0, 1.0, 0.0] for _ in texts]


def test_builder_restores_checkpoint_and_only_embeds_missing_chunks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    first_text = "Điều 1\nChương I\nNội dung đã lưu"
    checkpoint = _Checkpoint(
        {
            "chunk:first": (
                embedding_content_hash(first_text),
                [1.0, 0.0, 0.0],
            )
        }
    )
    embeddings = _Embeddings()

    monkeypatch.setenv("LEGAL_EMBEDDING_CHECKPOINT_ENABLED", "true")
    monkeypatch.setenv("LEGAL_EMBEDDING_CHECKPOINT_BATCH_SIZE", "1")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://test:test@postgres/test",
    )
    monkeypatch.setattr(
        "app.legal_graphrag.PostgresEmbeddingCheckpoint",
        lambda *_: checkpoint,
    )
    monkeypatch.setattr(
        "app.legal_graphrag.get_embedding_service",
        lambda *_: embeddings,
    )

    builder = LegalGraphBuilder(
        tmp_path,
        tmp_path,
        EmbeddingConfig(
            dimensions=3,
            project_id="test-project",
            use_adc=True,
        ),
    )
    builder.chunks = OrderedDict(
        [
            (
                "chunk:first",
                {
                    "chunk_id": "chunk:first",
                    "title": "Điều 1",
                    "path_label": "Chương I",
                    "text": "Nội dung đã lưu",
                    "vector": b"",
                },
            ),
            (
                "chunk:second",
                {
                    "chunk_id": "chunk:second",
                    "title": "Điều 2",
                    "path_label": "Chương I",
                    "text": "Nội dung mới",
                    "vector": b"",
                },
            ),
        ]
    )

    builder._embed_chunks()

    assert embeddings.calls == [["Điều 2\nChương I\nNội dung mới"]]
    assert list(blob_to_vector(builder.chunks["chunk:first"]["vector"])) == [
        1.0,
        0.0,
        0.0,
    ]
    assert list(blob_to_vector(builder.chunks["chunk:second"]["vector"])) == [
        0.0,
        1.0,
        0.0,
    ]
    assert [record.chunk_id for record in checkpoint.saved] == [
        "chunk:second"
    ]
