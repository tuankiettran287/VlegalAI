from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.embeddings import EmbeddingConfig, EmbeddingModelError, LocalEmbeddingService


class _Matrix:
    def __init__(self, rows: list[list[float]]):
        self.rows = rows

    def tolist(self) -> list[list[float]]:
        return self.rows


class _FakeSentenceTransformer:
    instances: list["_FakeSentenceTransformer"] = []

    def __init__(self, path: str, **kwargs):
        self.path = path
        self.kwargs = kwargs
        self.max_seq_length = 0
        self.calls: list[tuple[str, list[str], dict]] = []
        self.evaluating = False
        self.instances.append(self)

    def get_sentence_embedding_dimension(self) -> int:
        return 3

    def eval(self) -> None:
        self.evaluating = True

    def encode_document(self, texts: list[str], **kwargs) -> _Matrix:
        self.calls.append(("document", texts, kwargs))
        return _Matrix([[1.0, 0.0, 0.0] for _ in texts])

    def encode_query(self, texts: list[str], **kwargs) -> _Matrix:
        self.calls.append(("query", texts, kwargs))
        return _Matrix([[0.0, 1.0, 0.0] for _ in texts])


class LocalEmbeddingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeSentenceTransformer.instances.clear()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.model_dir = Path(self.temp_dir.name)
        (self.model_dir / "config.json").write_text("{}", encoding="utf-8")
        (self.model_dir / "modules.json").write_text("[]", encoding="utf-8")
        self.fake_module = types.SimpleNamespace(SentenceTransformer=_FakeSentenceTransformer)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def config(self, dimensions: int = 3) -> EmbeddingConfig:
        return EmbeddingConfig(
            model_path=str(self.model_dir),
            dimensions=dimensions,
            batch_size=7,
            max_sequence_length=1234,
        )

    def test_uses_document_and_query_routes_with_normalized_output(self) -> None:
        with patch.dict(sys.modules, {"sentence_transformers": self.fake_module}):
            service = LocalEmbeddingService(self.config())
            self.assertEqual(service.embed_documents(["điều luật"]), [[1.0, 0.0, 0.0]])
            self.assertEqual(service.embed_query("câu hỏi"), [0.0, 1.0, 0.0])

        model = _FakeSentenceTransformer.instances[0]
        self.assertEqual(model.max_seq_length, 1234)
        self.assertTrue(model.evaluating)
        self.assertEqual([call[0] for call in model.calls], ["document", "query"])
        for _, _, kwargs in model.calls:
            self.assertEqual(kwargs["batch_size"], 7)
            self.assertTrue(kwargs["normalize_embeddings"])
            self.assertTrue(kwargs["convert_to_numpy"])

    def test_rejects_configured_dimension_mismatch(self) -> None:
        with patch.dict(sys.modules, {"sentence_transformers": self.fake_module}):
            with self.assertRaisesRegex(EmbeddingModelError, "produces 3 dimensions"):
                LocalEmbeddingService(self.config(dimensions=2)).embed_query("query")

    def test_requires_complete_local_checkpoint(self) -> None:
        (self.model_dir / "modules.json").unlink()
        with self.assertRaisesRegex(EmbeddingModelError, "model-init"):
            LocalEmbeddingService(self.config()).embed_query("query")


if __name__ == "__main__":
    unittest.main()
