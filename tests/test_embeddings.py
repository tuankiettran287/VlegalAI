from __future__ import annotations

import json
import math
from types import SimpleNamespace

import httpx
import pytest

from app.services.embeddings import (
    EMBEDDING_PROVIDER_REVISION,
    GEMINI_API_PROVIDER_REVISION,
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


def test_vertex_batches_documents_and_preserves_order() -> None:
    requests: list[httpx.Request] = []
    vectors = {
        "one": [1.0, 0.0, 0.0],
        "two": [0.0, 2.0, 0.0],
        "three": [0.0, 0.0, 3.0],
        "four": [1.0, 1.0, 0.0],
        "five": [1.0, 0.0, 1.0],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        instances = json.loads(request.content)["instances"]
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {
                        "embeddings": {
                            "values": vectors[instance["content"]]
                        }
                    }
                    for instance in instances
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = VertexAIEmbeddingService(
        EmbeddingConfig(
            model="gemini-embedding-001",
            project_id="legal-project",
            location="asia-southeast1",
            dimensions=3,
            max_concurrency=1,
            batch_size=2,
            max_retries=1,
            data_policy="allow",
        ),
        client=client,
    )
    service._credentials = SimpleNamespace(valid=True, token="access-token")
    service._project_id = "legal-project"
    try:
        result = service.embed_documents(
            ["one", "two", "three", "four", "five"]
        )
    finally:
        client.close()

    assert result[0] == [1.0, 0.0, 0.0]
    assert result[1] == [0.0, 1.0, 0.0]
    assert result[2] == [0.0, 0.0, 1.0]
    assert result[3] == pytest.approx(
        [1 / math.sqrt(2), 1 / math.sqrt(2), 0.0]
    )
    assert result[4] == pytest.approx(
        [1 / math.sqrt(2), 0.0, 1 / math.sqrt(2)]
    )
    bodies = [json.loads(request.content) for request in requests]
    assert [len(body["instances"]) for body in bodies] == [2, 2, 1]
    assert [
        instance["content"]
        for body in bodies
        for instance in body["instances"]
    ] == ["one", "two", "three", "four", "five"]


def test_vertex_batch_counts_one_rate_limit_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        instances = json.loads(request.content)["instances"]
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {"embeddings": {"values": [1.0, 0.0, 0.0]}}
                    for _ in instances
                ]
            },
        )

    service, client = _service(handler)
    item_counts: list[int] = []
    monkeypatch.setattr(service, "_throttle_items", item_counts.append)
    try:
        service.embed_documents(["one", "two"])
    finally:
        client.close()

    assert item_counts == [1]


def test_vertex_batch_splits_after_request_size_rejection() -> None:
    instance_counts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        instances = json.loads(request.content)["instances"]
        instance_counts.append(len(instances))
        if len(instances) > 1:
            return httpx.Response(
                400,
                json={"error": {"message": "request exceeds token limit"}},
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
            model="gemini-embedding-001",
            project_id="legal-project",
            location="asia-southeast1",
            dimensions=3,
            max_concurrency=1,
            batch_size=2,
            max_retries=1,
            data_policy="allow",
        ),
        client=client,
    )
    service._credentials = SimpleNamespace(valid=True, token="access-token")
    service._project_id = "legal-project"
    try:
        result = service.embed_documents(["one", "two"])
    finally:
        client.close()

    assert result == [[1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    assert instance_counts == [2, 1, 1]


def test_vertex_logs_truncated_inputs_with_content_hash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "predictions": [
                    {
                        "embeddings": {
                            "values": [1.0, 0.0, 0.0],
                            "statistics": {
                                "token_count": 2048,
                                "truncated": True,
                            },
                        }
                    }
                ]
            },
        )

    service, client = _service(handler)
    try:
        with caplog.at_level("WARNING"):
            service.embed_documents(["oversized legal text"])
    finally:
        client.close()

    assert "Vertex AI truncated embedding input" in caplog.text
    assert "token_count=2048" in caplog.text
    assert "content_sha256=" in caplog.text


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

    rate_limited = EmbeddingConfig(
        use_adc=True,
        batch_size=20,
        max_items_per_minute=4,
    )
    assert rate_limited.ready


def test_gemini_api_batches_documents_and_preserves_order() -> None:
    requests: list[httpx.Request] = []
    vectors = {
        "one": [1.0, 0.0, 0.0],
        "two": [0.0, 2.0, 0.0],
        "three": [0.0, 0.0, 3.0],
        "four": [1.0, 1.0, 0.0],
        "five": [1.0, 0.0, 1.0],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        embed_requests = body.get("requests", [body])
        embeddings = [
            {
                "values": vectors[
                    embed_request["content"]["parts"][0]["text"]
                ]
            }
            for embed_request in embed_requests
        ]
        if len(embed_requests) == 1:
            return httpx.Response(200, json={"embedding": embeddings[0]})
        return httpx.Response(200, json={"embeddings": embeddings})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = VertexAIEmbeddingService(
        EmbeddingConfig(
            provider="gemini-api",
            model="gemini-embedding-001",
            api_key="test-api-key",
            dimensions=3,
            max_concurrency=1,
            batch_size=2,
            max_retries=1,
            data_policy="allow",
        ),
        client=client,
    )
    try:
        result = service.embed_documents(
            ["one", "two", "three", "four", "five"]
        )
    finally:
        client.close()

    assert len(result) == 5
    assert result[0] == [1.0, 0.0, 0.0]
    assert result[1] == [0.0, 1.0, 0.0]
    assert result[2] == [0.0, 0.0, 1.0]
    assert result[3] == pytest.approx(
        [1 / math.sqrt(2), 1 / math.sqrt(2), 0.0]
    )
    assert result[4] == pytest.approx(
        [1 / math.sqrt(2), 0.0, 1 / math.sqrt(2)]
    )
    assert [request.url.path.rsplit(":", 1)[-1] for request in requests] == [
        "batchEmbedContents",
        "batchEmbedContents",
        "embedContent",
    ]
    for request in requests:
        assert request.headers["x-goog-api-key"] == "test-api-key"
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        for embed_request in body.get("requests", [body]):
            assert embed_request["model"] == "models/gemini-embedding-001"
            assert embed_request["taskType"] == "RETRIEVAL_DOCUMENT"
            assert embed_request["outputDimensionality"] == 3


def test_gemini_api_config_requires_key_and_tracks_provider() -> None:
    missing_key = EmbeddingConfig(provider="gemini-api", api_key="")
    configured = EmbeddingConfig(
        provider="gemini_api",
        api_key="test-api-key",
    )

    assert not missing_key.ready
    assert configured.ready
    assert (
        configured.model_revision
        == f"{GEMINI_API_PROVIDER_REVISION}:redact"
    )
    assert configured.identity == "gemini-embedding-001@gemini-api-v1:redact"


def test_embedding_rate_limiter_counts_items_inside_batches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = [100.0]
    sleeps: list[float] = []

    monkeypatch.setattr(
        "app.services.embeddings.time.monotonic",
        lambda: current_time[0],
    )

    def advance_time(seconds: float) -> None:
        sleeps.append(seconds)
        current_time[0] += seconds

    monkeypatch.setattr(
        "app.services.embeddings.time.sleep",
        advance_time,
    )

    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(500)
        )
    )
    service = VertexAIEmbeddingService(
        EmbeddingConfig(
            provider="gemini-api",
            api_key="test-api-key",
            max_items_per_minute=2,
        ),
        client=client,
    )
    try:
        service._throttle_items(2)
        service._throttle_items(1)
    finally:
        client.close()

    assert sleeps == [60.0]


def test_vertex_request_is_counted_by_the_shared_rate_limiter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, client = _service(
        lambda _: httpx.Response(
            200,
            json={
                "predictions": [
                    {"embeddings": {"values": [1.0, 0.0, 0.0]}}
                ]
            },
        )
    )
    item_counts: list[int] = []
    monkeypatch.setattr(
        service,
        "_throttle_items",
        item_counts.append,
    )
    try:
        service.embed_query("quota-safe query")
    finally:
        client.close()

    assert item_counts == [1]


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
