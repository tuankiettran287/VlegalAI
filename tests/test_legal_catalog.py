from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from app.services.legal_catalog import (
    CatalogRequest,
    LegalCatalogService,
    parse_catalog_request,
)


class _Mappings:
    def __init__(self, rows):
        self.rows = rows

    def one(self):
        assert len(self.rows) == 1
        return self.rows[0]

    def all(self):
        return self.rows


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return _Mappings(self.rows)


class _CatalogDB:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, statement, parameters):
        sql = str(statement)
        self.statements.append(sql)
        if "SELECT *" in sql:
            return _Result(
                [
                    {
                        "catalog_total": 2,
                        "law_code_normalized": "01/2026/ND-CP",
                        "code": "01/2026/NĐ-CP",
                        "title": "Nghị định thứ nhất",
                        "document_type": "DECREE",
                        "issuer": "Chính phủ",
                        "source_url": "https://example.test/1",
                        "corpus_status": "IN_FORCE",
                        "resolved_status": "IN_FORCE",
                        "status_source": "VERIFIED_DOCUMENT",
                        "status_conflict": False,
                        "metadata_verified": True,
                        "effective_from": None,
                        "effective_to": None,
                        "replaced_by_code": None,
                        "verified_at": None,
                        "law_version": 1,
                        "chunk_count": 10,
                        "indexed_at": None,
                        "refreshed_at": datetime(2026, 7, 29, tzinfo=UTC),
                    },
                    {
                        "catalog_total": 2,
                        "law_code_normalized": "02/2026/ND-CP",
                        "code": "02/2026/NĐ-CP",
                        "title": "Nghị định thứ hai",
                        "document_type": "DECREE",
                        "issuer": "",
                        "source_url": None,
                        "corpus_status": "UNVERIFIED",
                        "resolved_status": "UNVERIFIED",
                        "status_source": "INDEXED_CORPUS",
                        "status_conflict": False,
                        "metadata_verified": False,
                        "effective_from": None,
                        "effective_to": None,
                        "replaced_by_code": None,
                        "verified_at": None,
                        "law_version": 1,
                        "chunk_count": 5,
                        "indexed_at": None,
                        "refreshed_at": datetime(2026, 7, 29, tzinfo=UTC),
                    },
                ]
            )
        raise AssertionError(sql)


class _StatsCatalogDB:
    async def execute(self, statement, parameters):
        sql = str(statement)
        if "count(*)::bigint AS total" in sql:
            return _Result(
                [
                    {
                        "total": 3,
                        "metadata_verified": 2,
                        "metadata_unverified": 1,
                        "missing_source_url": 1,
                        "status_conflicts": 0,
                        "as_of": datetime(2026, 7, 29, tzinfo=UTC),
                    }
                ]
            )
        if "GROUP BY document_type" in sql:
            return _Result(
                [
                    {"key": "DECREE", "count": 2},
                    {"key": "LAW", "count": 1},
                ]
            )
        if "GROUP BY resolved_status" in sql:
            return _Result(
                [
                    {"key": "IN_FORCE", "count": 2},
                    {"key": "UNVERIFIED", "count": 1},
                ]
            )
        raise AssertionError(sql)


def test_catalog_intent_requires_explicit_vlegal_scope() -> None:
    assert parse_catalog_request(
        "Có bao nhiêu nghị định trong kho VLegal?"
    ) == CatalogRequest(action="count", document_type="DECREE")
    assert parse_catalog_request(
        "Liệt kê các nghị định đang có hiệu lực trong corpus VLegal"
    ) == CatalogRequest(
        action="list",
        document_type="DECREE",
        status="CURRENT",
    )
    assert parse_catalog_request(
        "Có bao nhiêu nghị định của Việt Nam?"
    ) is None
    assert parse_catalog_request(
        "Nghị định 118 có bao nhiêu Điều?"
    ) is None


def test_catalog_intent_recognizes_vlegal_summary_wording() -> None:
    assert parse_catalog_request(
        "Thống kê văn bản theo loại và hiệu lực trong kho dữ liệu VLegal"
    ) == CatalogRequest(action="summary")
    assert parse_catalog_request(
        "Thống kê nghị định đang có hiệu lực trong kho luật VLegal"
    ) == CatalogRequest(
        action="summary",
        document_type="DECREE",
        status="CURRENT",
    )
    assert parse_catalog_request(
        "Thống kê nghị định đang có hiệu lực tại Việt Nam"
    ) is None


def test_catalog_answer_states_its_corpus_scope_and_preserves_unknown() -> None:
    db = _CatalogDB()
    service = LegalCatalogService(db)  # type: ignore[arg-type]

    answer = asyncio.run(
        service.answer(
            CatalogRequest(action="list", document_type="DECREE")
        )
    )

    assert "Kho VLegal hiện có 2 nghị định" in answer
    assert "không phải toàn bộ hệ thống văn bản pháp luật Việt Nam" in answer
    assert "chưa được kiểm chứng" in answer
    assert any(
        "status_source" in statement
        and "document.verified_at IS NOT NULL" in statement
        for statement in db.statements
    )


def test_current_status_filter_includes_literal_current_status() -> None:
    db = _CatalogDB()
    service = LegalCatalogService(db)  # type: ignore[arg-type]

    asyncio.run(service.documents(status="CURRENT"))

    assert any(
        "'CURRENT', 'IN_FORCE', 'PARTIALLY_IN_FORCE', 'AMENDED'"
        in statement
        for statement in db.statements
    )


def test_catalog_summary_uses_direct_sql_group_counts() -> None:
    service = LegalCatalogService(_StatsCatalogDB())  # type: ignore[arg-type]

    answer = asyncio.run(service.answer(CatalogRequest(action="summary")))

    assert "Kho VLegal hiện có 3 văn bản đã index" in answer
    assert "nghị định: 2" in answer
    assert "luật: 1" in answer
    assert "đang có hiệu lực: 2" in answer
    assert "chưa được kiểm chứng: 1" in answer
