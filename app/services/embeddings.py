from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EMBEDDING_REPO = "BAAI/bge-m3"
DEFAULT_EMBEDDING_DIMENSIONS = 1024


class EmbeddingModelError(RuntimeError):
    """Raised when the local embedding checkpoint cannot be loaded or used."""


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    model_path: str = str(PROJECT_ROOT / "models" / "bge-m3")
    model_repo: str = DEFAULT_EMBEDDING_REPO
    model_revision: str = "main"
    device: str = "auto"
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS
    batch_size: int = 4
    max_sequence_length: int = 2048

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        return cls(
            model_path=os.getenv("EMBEDDING_MODEL_PATH", str(PROJECT_ROOT / "models" / "bge-m3")),
            model_repo=os.getenv("EMBEDDING_MODEL_REPO", DEFAULT_EMBEDDING_REPO),
            model_revision=os.getenv("EMBEDDING_MODEL_REVISION", "main"),
            device=os.getenv("EMBEDDING_DEVICE", "auto").strip().lower(),
            dimensions=int(os.getenv("POSTGRES_VECTOR_SIZE", str(DEFAULT_EMBEDDING_DIMENSIONS))),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "4")),
            max_sequence_length=int(os.getenv("EMBEDDING_MAX_SEQUENCE_LENGTH", "2048")),
        )

    @property
    def local_path(self) -> Path:
        path = Path(self.model_path).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def identity(self) -> str:
        return f"{self.model_repo}@{self.model_revision}"

    @property
    def ready(self) -> bool:
        path = self.local_path
        return path.is_dir() and (path / "config.json").is_file() and (path / "modules.json").is_file()


class LocalEmbeddingService:
    """Thread-safe Sentence Transformers inference from a local checkpoint."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._model: Any = None
        self._load_lock = threading.Lock()
        self._encode_lock = threading.Lock()

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            if not self.config.ready:
                raise EmbeddingModelError(
                    f"Embedding checkpoint is not available at {self.config.local_path}. "
                    "Run the model-init service first."
                )
            try:
                from sentence_transformers import SentenceTransformer

                device = None if self.config.device == "auto" else self.config.device
                model = SentenceTransformer(
                    str(self.config.local_path),
                    device=device,
                    trust_remote_code=False,
                    local_files_only=True,
                )
                model.max_seq_length = self.config.max_sequence_length
                dimensions = int(model.get_sentence_embedding_dimension() or 0)
                if dimensions != self.config.dimensions:
                    raise EmbeddingModelError(
                        f"Embedding model produces {dimensions} dimensions, but "
                        f"POSTGRES_VECTOR_SIZE={self.config.dimensions}."
                    )
                model.eval()
                self._model = model
            except EmbeddingModelError:
                raise
            except Exception as exc:
                raise EmbeddingModelError(f"Cannot load embedding model: {exc}") from exc
        return self._model

    def _encode(self, texts: list[str], *, query: bool, show_progress: bool = False) -> list[list[float]]:
        if not texts:
            return []
        model = self._load()
        method_name = "encode_query" if query else "encode_document"
        encode = getattr(model, method_name, None) or model.encode
        with self._encode_lock:
            try:
                values = encode(
                    texts,
                    batch_size=self.config.batch_size,
                    show_progress_bar=show_progress,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                )
            except Exception as exc:
                raise EmbeddingModelError(f"Embedding inference failed: {exc}") from exc
        rows = values.tolist() if hasattr(values, "tolist") else list(values)
        result = [[float(value) for value in row] for row in rows]
        if any(len(row) != self.config.dimensions for row in result):
            raise EmbeddingModelError("Embedding output has an unexpected dimension.")
        return result

    def embed_documents(self, texts: Iterable[str], *, show_progress: bool = False) -> list[list[float]]:
        return self._encode([str(text or "") for text in texts], query=False, show_progress=show_progress)

    def embed_query(self, text: str) -> list[float]:
        rows = self._encode([str(text or "")], query=True)
        return rows[0]


@lru_cache(maxsize=8)
def get_embedding_service(config: EmbeddingConfig | None = None) -> LocalEmbeddingService:
    return LocalEmbeddingService(config or EmbeddingConfig.from_env())
