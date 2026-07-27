from __future__ import annotations

import json
import math
from types import SimpleNamespace

import httpx
import pytest

from app.services.embeddings import (
    EMBEDDING_PROVIDER_REVISION,
    EmbeddingConfig,
    EmbeddingModelError,
    VertexAIEmbeddingService,
)


def _service(
    handler,
    *,
    dimensions: int = 3,
) -> tuple[VertexAIEmbeddingService, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = VertexAIEmbeddingService(
        EmbeddingConfig(
            model="gemini-embedding-001",
            project_id="legal-project",
            location="asia-southeast1",
            dimensions=dimensions,
            max_concurrency=1,
            max_retries=1,
        ),
        client=client,
    )
    service._credentials = SimpleNamespace(valid=True, token="access-token")
    service._project_id = "legal-project"
    return service, client


def test_uses_vertex_document_and_query_task_types_and_normalizes_output() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"embeddings": {"values": [3.0, 4.0, 0.0]}}
                ]
            },
        )

    service, client = _service(handler)
    try:
        document = service.embed_documents(["điều luật"])
        query = service.embed_query("câu hỏi")
        similarity = service.embed_similarity("câu hỏi tương tự")
    finally:
        client.close()

    assert document == [[0.6, 0.8, 0.0]]
    assert query == [0.6, 0.8, 0.0]
    assert similarity == [0.6, 0.8, 0.0]
    bodies = [json.loads(request.content) for request in requests]
    assert [body["instances"][0]["task_type"] for body in bodies] == [
        "RETRIEVAL_DOCUMENT",
        "RETRIEVAL_QUERY",
        "SEMANTIC_SIMILARITY",
    ]
    for request, body in zip(requests, bodies, strict=True):
        assert request.headers["authorization"] == "Bearer access-token"
        assert body["parameters"] == {
            "autoTruncate": True,
            "outputDimensionality": 3,
        }
        assert request.url == (
            "https://asia-southeast1-aiplatform.googleapis.com/v1/projects/legal-project/"
            "locations/asia-southeast1/publishers/google/models/"
            "gemini-embedding-001:predict"
        )


def test_rejects_vertex_dimension_mismatch() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"embeddings": {"values": [1.0, 0.0]}}
                ]
            },
        )

    service, client = _service(handler)
    try:
        with pytest.raises(EmbeddingModelError, match="returned 2 dimensions"):
            service.embed_query("query")
    finally:
        client.close()


def test_rejects_zero_magnitude_vector() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"embeddings": {"values": [0.0, 0.0, 0.0]}}
                ]
            },
        )

    service, client = _service(handler)
    try:
        with pytest.raises(EmbeddingModelError, match="zero magnitude"):
            service.embed_query("query")
    finally:
        client.close()


def test_embedding_config_identity_tracks_vertex_provider() -> None:
    config = EmbeddingConfig()

    assert config.model == "gemini-embedding-001"
    assert config.model_revision == f"{EMBEDDING_PROVIDER_REVISION}:redact"
    assert config.identity == "gemini-embedding-001@vertex-ai-v1:redact"
    assert 128 <= config.dimensions <= 3072
    assert math.isfinite(config.timeout_seconds)


def test_global_location_uses_the_global_vertex_hostname() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == (
            "https://aiplatform.googleapis.com/v1/projects/legal-project/"
            "locations/global/publishers/google/models/"
            "gemini-embedding-001:predict"
        )
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"embeddings": {"values": [1.0, 0.0, 0.0]}}
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = VertexAIEmbeddingService(
        EmbeddingConfig(
            project_id="legal-project",
            location="global",
            dimensions=3,
            max_concurrency=1,
            max_retries=1,
        ),
        client=client,
    )
    service._credentials = SimpleNamespace(valid=True, token="access-token")
    service._project_id = "legal-project"
    try:
        assert service.embed_query("query") == [1.0, 0.0, 0.0]
    finally:
        client.close()


def test_rejects_invalid_vertex_location_before_sending_a_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = VertexAIEmbeddingService(
        EmbeddingConfig(
            project_id="legal-project",
            location="evil.example/path",
            dimensions=3,
            max_concurrency=1,
            max_retries=1,
        ),
        client=client,
    )
    service._credentials = SimpleNamespace(valid=True, token="access-token")
    service._project_id = "legal-project"
    try:
        with pytest.raises(EmbeddingModelError, match="valid location"):
            service.embed_query("query")
    finally:
        client.close()

    assert requests == []


def test_redacts_sensitive_text_before_vertex_embedding_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"embeddings": {"values": [1.0, 0.0, 0.0]}}
                ]
            },
        )

    service, client = _service(handler)
    try:
        service.embed_query("Liên hệ luật sư qua an@example.com")
    finally:
        client.close()

    body = json.loads(requests[0].content)
    content = body["instances"][0]["content"]
    assert "an@example.com" not in content
    assert "[REDACTED_EMAIL]" in content


def test_deny_policy_blocks_sensitive_embedding_without_network_call() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = VertexAIEmbeddingService(
        EmbeddingConfig(
            project_id="legal-project",
            location="asia-southeast1",
            dimensions=3,
            max_concurrency=1,
            max_retries=1,
            data_policy="deny",
        ),
        client=client,
    )
    try:
        with pytest.raises(EmbeddingModelError, match="Sensitive data"):
            service.embed_query("Liên hệ luật sư qua an@example.com")
    finally:
        client.close()

    assert requests == []
