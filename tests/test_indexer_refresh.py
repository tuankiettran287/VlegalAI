from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.models import LegalDocument
from app.services import indexer as indexer_module
from app.services.indexer import (
    LegalCandidate,
    LegalIndexer,
    UnsafeLegalSourceError,
    chunk_legal_text,
    download_legal_text,
)


class _RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def run(self, query: str, **parameters: object) -> None:
        self.calls.append((query, parameters))


class _SessionContext(_RecordingSession):
    def __enter__(self) -> "_SessionContext":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def begin_transaction(self) -> "_SessionContext":
        return self


class _RecordingDriver:
    def __init__(self) -> None:
        self.recording_session = _SessionContext()
        self.closed = False

    def session(self, **_: object) -> _SessionContext:
        return self.recording_session

    def close(self) -> None:
        self.closed = True


def test_replacement_link_supports_legacy_graph_document_number() -> None:
    session = _RecordingSession()
    document = SimpleNamespace(
        id="new-document",
        external_doc_id=None,
        code="200/2025/QH15",
        version=1,
        status="IN_FORCE",
    )

    LegalIndexer._link_replacement(session, document, "100/2020/QH14")

    query, parameters = session.calls[0]
    assert "old.number" in query
    assert "MERGE (new)-[:REPLACES]->(old)" in query
    assert "old_chunk.law_status = 'REPLACED'" in query
    assert parameters["old_code"] == "100/2020/QH14"


class _ExistingDocumentDb:
    def __init__(
        self,
        document: SimpleNamespace,
        chunks: list[SimpleNamespace] | None = None,
    ) -> None:
        self.document = document
        self.chunks = list(chunks or [])
        self.executed: list[tuple[object, object]] = []
        self.added: list[object] = []

    async def scalar(self, _: object) -> SimpleNamespace:
        return self.document

    async def execute(self, statement: object, parameters: object = None) -> None:
        self.executed.append((statement, parameters))

    async def scalars(self, _: object) -> SimpleNamespace:
        return SimpleNamespace(all=lambda: self.chunks)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


def test_unchanged_replacement_still_syncs_replaces_relation(monkeypatch) -> None:
    legal_text = "Luật số 200/2025/QH15. Nội dung văn bản thay thế. " * 30

    async def fake_download(_: str, **__: object) -> tuple[str, str]:
        return legal_text, "https://vanban.chinhphu.vn/luat-moi"

    document = SimpleNamespace(
        id="new-document",
        external_doc_id=None,
        code="200/2025/QH15",
        version=1,
        status="IN_FORCE",
        source_url="https://vanban.chinhphu.vn/luat-moi",
        checksum=indexer_module.hashlib.sha256(legal_text.encode("utf-8")).hexdigest(),
    )
    chunk = SimpleNamespace(
        external_chunk_id="new-chunk-1",
        node_id="law:200/2025/QH15:v1:section:0",
        chunk_type="article",
        title="Luật mới",
        citation="200/2025/QH15 — Điều 1",
        text="Điều 1. Phạm vi điều chỉnh",
        ordinal=0,
    )
    synced: list[tuple[object, list[object], str | None]] = []
    service = LegalIndexer(Settings(_env_file=None))
    monkeypatch.setattr(indexer_module, "download_legal_text", fake_download)
    monkeypatch.setattr(
        service,
        "_sync_external",
        lambda current, chunks, old_code: synced.append(
            (current, chunks, old_code)
        ),
    )

    result = asyncio.run(
        service.index_candidate(
            _ExistingDocumentDb(document, [chunk]),
            LegalCandidate(
                code="200/2025/QH15",
                title="Luật mới",
                url="https://vanban.chinhphu.vn/luat-moi",
                status="IN_FORCE",
                replaces_code="100/2020/QH14",
            ),
        )
    )

    assert result is document
    assert synced == [(document, [chunk], "100/2020/QH14")]


def test_indexer_rejects_redirect_from_official_source_to_external_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_download(_: str, **__: object) -> tuple[str, str]:
        return (
            "Luật số 200/2025/QH15. Nội dung văn bản chính thức. " * 30,
            "https://attacker.example/redirected-law",
        )

    service = LegalIndexer(Settings(_env_file=None))
    monkeypatch.setattr(indexer_module, "download_legal_text", fake_download)

    with pytest.raises(ValueError, match="sau chuyển hướng"):
        asyncio.run(
            service.index_candidate(
                _ExistingDocumentDb(SimpleNamespace()),
                LegalCandidate(
                    code="200/2025/QH15",
                    title="Luật mới",
                    url="https://vanban.chinhphu.vn/luat-moi",
                    status="IN_FORCE",
                ),
            )
        )


def test_download_rejects_external_redirect_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.host == "vanban.chinhphu.vn":
            return httpx.Response(
                302,
                headers={"Location": "https://attacker.example/private"},
                request=request,
            )
        raise AssertionError("Unsafe redirect target must never be requested")

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(indexer_module.httpx, "AsyncClient", client_factory)

    with pytest.raises(UnsafeLegalSourceError, match="sau chuyển hướng"):
        asyncio.run(
            download_legal_text(
                "https://vanban.chinhphu.vn/luat-moi",
                allowed_domains=["vanban.chinhphu.vn"],
            )
        )

    assert requested_urls == ["https://vanban.chinhphu.vn/luat-moi"]


def test_download_rejects_https_downgrade_before_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "http://vanban.chinhphu.vn/luat-moi"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(indexer_module.httpx, "AsyncClient", client_factory)

    with pytest.raises(UnsafeLegalSourceError, match="HTTPS"):
        asyncio.run(
            download_legal_text(
                "https://vanban.chinhphu.vn/luat-moi",
                allowed_domains=["vanban.chinhphu.vn"],
            )
        )

    assert requested_urls == ["https://vanban.chinhphu.vn/luat-moi"]


def test_unsafe_download_failure_never_uses_candidate_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unsafe_download(*_: object, **__: object) -> tuple[str, str]:
        raise UnsafeLegalSourceError("unsafe redirect")

    service = LegalIndexer(Settings(_env_file=None))
    monkeypatch.setattr(indexer_module, "download_legal_text", unsafe_download)

    with pytest.raises(UnsafeLegalSourceError, match="unsafe redirect"):
        asyncio.run(
            service.index_candidate(
                _ExistingDocumentDb(SimpleNamespace()),
                LegalCandidate(
                    code="200/2025/QH15",
                    title="Luật mới",
                    url="https://vanban.chinhphu.vn/luat-moi",
                    status="IN_FORCE",
                    content="Nội dung fallback không được sử dụng. " * 40,
                ),
            )
        )


@pytest.mark.parametrize("failure", [httpx.ConnectError("offline"), ValueError("bad PDF")])
def test_download_or_extraction_failure_never_uses_provider_content(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    async def failed_download(*_: object, **__: object) -> tuple[str, str]:
        raise failure

    service = LegalIndexer(Settings(_env_file=None))
    monkeypatch.setattr(indexer_module, "download_legal_text", failed_download)

    with pytest.raises(type(failure), match=str(failure)):
        asyncio.run(
            service.index_candidate(
                _ExistingDocumentDb(SimpleNamespace()),
                LegalCandidate(
                    code="200/2025/QH15",
                    title="Luật mới",
                    url="https://vanban.chinhphu.vn/luat-moi",
                    status="IN_FORCE",
                    content=(
                        "Luật số 200/2025/QH15. Nội dung do nhà cung cấp gửi. "
                        * 30
                    ),
                ),
            )
        )


def test_indexer_rejects_download_that_only_contains_code_as_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_download(*_: object, **__: object) -> tuple[str, str]:
        return (
            "Văn bản số 200/2025/QH15X không phải mã được yêu cầu. " * 30,
            "https://vanban.chinhphu.vn/luat-moi",
        )

    service = LegalIndexer(Settings(_env_file=None))
    monkeypatch.setattr(indexer_module, "download_legal_text", fake_download)

    with pytest.raises(UnsafeLegalSourceError, match="đúng mã văn bản"):
        asyncio.run(
            service.index_candidate(
                _ExistingDocumentDb(SimpleNamespace()),
                LegalCandidate(
                    code="200/2025/QH15",
                    title="Luật mới",
                    url="https://vanban.chinhphu.vn/luat-moi",
                    status="IN_FORCE",
                ),
            )
        )


def test_indexer_normalizes_code_and_takes_transaction_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legal_text = "Luật số 200 / 2025 / QH15. Nội dung chính thức. " * 30

    async def fake_download(*_: object, **__: object) -> tuple[str, str]:
        return legal_text, "https://vanban.chinhphu.vn/luat-moi"

    document = SimpleNamespace(
        id="document",
        external_doc_id=None,
        code="200/2025/QH15",
        version=1,
        status="IN_FORCE",
        source_url="https://vanban.chinhphu.vn/luat-moi",
        checksum=indexer_module.hashlib.sha256(legal_text.encode("utf-8")).hexdigest(),
    )
    db = _ExistingDocumentDb(document)
    service = LegalIndexer(Settings(_env_file=None))
    monkeypatch.setattr(indexer_module, "download_legal_text", fake_download)
    monkeypatch.setattr(service, "_sync_external", lambda *_: None)

    result = asyncio.run(
        service.index_candidate(
            db,
            LegalCandidate(
                code=" 200 / 2025 / qh15 ",
                title="Luật mới",
                url="https://vanban.chinhphu.vn/luat-moi",
                status="IN_FORCE",
            ),
        )
    )

    assert result is document
    assert db.executed
    assert db.executed[0][1] == {
        "lock_key": "legal-document:200/2025/QH15"
    }


def test_download_caps_response_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={
                "Content-Type": "text/html",
                "Content-Length": "100",
            },
            content=b"x" * 100,
            request=request,
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(indexer_module.httpx, "AsyncClient", client_factory)

    with pytest.raises(UnsafeLegalSourceError, match="kích thước"):
        asyncio.run(
            download_legal_text(
                "https://vanban.chinhphu.vn/luat-moi",
                allowed_domains=["vanban.chinhphu.vn"],
                max_bytes=32,
            )
        )


def test_download_caps_extracted_text(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"<html><body>" + (b"x" * 100) + b"</body></html>",
            request=request,
        )

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def client_factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_async_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr(indexer_module.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(indexer_module, "MAX_LEGAL_DOCUMENT_TEXT_CHARS", 32)

    with pytest.raises(UnsafeLegalSourceError, match="giải nén"):
        asyncio.run(
            download_legal_text(
                "https://vanban.chinhphu.vn/luat-moi",
                allowed_domains=["vanban.chinhphu.vn"],
            )
        )


def test_chunking_has_a_hard_chunk_count_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(indexer_module, "MAX_LEGAL_DOCUMENT_CHUNKS", 1)
    candidate = LegalCandidate(
        code="200/2025/QH15",
        title="Luật mới",
        url="https://vanban.chinhphu.vn/luat-moi",
        status="IN_FORCE",
    )

    with pytest.raises(UnsafeLegalSourceError, match="quá nhiều chunk"):
        chunk_legal_text(
            candidate,
            "Điều 1. Nội dung thứ nhất.\nĐiều 2. Nội dung thứ hai.",
            1,
        )


@pytest.mark.parametrize(
    "url",
    [
        "file://vanban.chinhphu.vn/luat-moi",
        "javascript://vanban.chinhphu.vn/luat-moi",
        "http://vanban.chinhphu.vn/luat-moi",
        "https://vanban.chinhphu.vn.attacker.example/luat-moi",
    ],
)
def test_indexer_rejects_non_http_or_spoofed_official_url(url: str) -> None:
    service = LegalIndexer(Settings(_env_file=None))

    with pytest.raises(ValueError, match="nguồn chính thức"):
        asyncio.run(
            service.index_candidate(
                _ExistingDocumentDb(SimpleNamespace()),
                LegalCandidate(
                    code="200/2025/QH15",
                    title="Luật mới",
                    url=url,
                    status="IN_FORCE",
                ),
            )
        )


def test_legal_document_normalizes_code_and_has_unique_expression_index() -> None:
    document = LegalDocument(code=" 200 / 2025 / qh15 ", title="Luật mới")

    assert document.code == "200/2025/QH15"
    index = next(
        item
        for item in LegalDocument.__table__.indexes
        if item.name == "uq_legal_document_code_normalized"
    )
    assert index.unique is True
    assert "regexp_replace" in str(next(iter(index.expressions))).lower()


def test_external_sync_upserts_embeddings_and_graph_replacement(monkeypatch) -> None:
    service = LegalIndexer(
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://test:test@postgres:5432/test",
            neo4j_password="secret",
        )
    )
    document = SimpleNamespace(
        id="new-document",
        external_doc_id="new-doc-id",
        code="200/2025/QH15",
        title="Luật mới",
        source_url="https://vanban.chinhphu.vn/luat-moi",
        version=1,
        status="IN_FORCE",
    )
    chunks = [
        SimpleNamespace(
            external_chunk_id="new-chunk-1",
            node_id="law:200/2025/QH15:v1:section:0",
            chunk_type="article",
            title="Luật mới",
            citation="200/2025/QH15 — Điều 1",
            text="Điều 1. Phạm vi điều chỉnh",
            ordinal=0,
        )
    ]
    upserted: list[list[dict]] = []
    marked: list[str] = []
    driver = _RecordingDriver()
    monkeypatch.setattr(indexer_module, "ensure_postgres_schema", lambda _: None)
    monkeypatch.setattr(indexer_module, "ensure_neo4j_schema", lambda *_: None)
    monkeypatch.setattr(
        indexer_module,
        "upsert_postgres_chunks",
        lambda rows, _: upserted.append(list(rows)),
    )
    monkeypatch.setattr(
        indexer_module.GraphDatabase,
        "driver",
        lambda *_args, **_kwargs: driver,
    )
    monkeypatch.setattr(
        service,
        "_mark_postgres_replaced",
        lambda _config, old_code: marked.append(old_code),
    )

    service._sync_external(document, chunks, "100/2020/QH14")

    assert upserted[0][0]["chunk_id"] == "new-chunk-1"
    assert upserted[0][0]["law_code"] == "200/2025/QH15"
    chunk_query, chunk_parameters = next(
        (query, parameters)
        for query, parameters in driver.recording_session.calls
        if "MERGE (c:LegalChunk" in query
    )
    assert "c.law_code=$code" in chunk_query
    assert "c.law_version=$version" in chunk_query
    assert chunk_parameters["code"] == "200/2025/QH15"
    assert marked == ["100/2020/QH14"]
    assert any("MERGE (c:LegalChunk" in query for query, _ in driver.recording_session.calls)
    assert any("MERGE (new)-[:REPLACES]->(old)" in query for query, _ in driver.recording_session.calls)
    assert driver.closed


def test_external_sync_does_not_replace_old_law_when_new_graph_sync_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailingSession(_SessionContext):
        def run(self, query: str, **parameters: object) -> None:
            super().run(query, **parameters)
            if "MERGE (c:LegalChunk" in query:
                raise RuntimeError("neo4j chunk write failed")

    class _FailingDriver(_RecordingDriver):
        def __init__(self) -> None:
            self.recording_session = _FailingSession()
            self.closed = False

    service = LegalIndexer(
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://test:test@postgres:5432/test",
            neo4j_password="secret",
        )
    )
    document = SimpleNamespace(
        id="new-document",
        external_doc_id="new-doc-id",
        code="200/2025/QH15",
        title="Luật mới",
        source_url="https://vanban.chinhphu.vn/luat-moi",
        version=1,
        status="IN_FORCE",
    )
    chunks = [
        SimpleNamespace(
            external_chunk_id="new-chunk-1",
            node_id="law:200/2025/QH15:v1:section:0",
            chunk_type="article",
            title="Luật mới",
            citation="200/2025/QH15 — Điều 1",
            text="Điều 1. Phạm vi điều chỉnh",
            ordinal=0,
        )
    ]
    marked: list[str] = []
    driver = _FailingDriver()
    monkeypatch.setattr(indexer_module, "ensure_postgres_schema", lambda _: None)
    monkeypatch.setattr(indexer_module, "ensure_neo4j_schema", lambda *_: None)
    monkeypatch.setattr(
        indexer_module,
        "upsert_postgres_chunks",
        lambda *_: 1,
    )
    monkeypatch.setattr(
        indexer_module.GraphDatabase,
        "driver",
        lambda *_args, **_kwargs: driver,
    )
    monkeypatch.setattr(
        service,
        "_sync_replacement_state",
        lambda _document, old_code: marked.append(old_code),
    )

    with pytest.raises(RuntimeError, match="neo4j chunk write failed"):
        service._sync_external(document, chunks, "100/2020/QH14")

    assert marked == []
    assert driver.closed
