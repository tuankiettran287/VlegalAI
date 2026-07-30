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
    # Câu hỏi về số Điều của văn bản cụ thể → article_count (hành vi đúng)
    result = parse_catalog_request("Nghị định 118 có bao nhiêu Điều?")
    assert result is not None
    assert result.action == "article_count"



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



# ---------------------------------------------------------------------------
# Article-count bug regression tests (bug: SQL thiếu WHERE law_code filter)
# ---------------------------------------------------------------------------

class _ArticleCountDB:
    """Mock DB cho article_count — trả 220 khi SQL có :normalized_code param."""

    def __init__(self, *, raise_on_count: bool = False, empty_result: bool = False):
        self.statements: list[str] = []
        self.params: list[dict] = []
        self.raise_on_count = raise_on_count
        self.empty_result = empty_result

    async def execute(self, statement, parameters=None):
        sql = str(statement)
        self.statements.append(sql)
        self.params.append(parameters or {})

        if "legal_catalog_corpus" in sql and "title ILIKE" in sql:
            # name_hint resolution query
            return _Result(
                [
                    {
                        "law_code_normalized": "45/2019/QH14",
                        "title": "Bộ luật Lao động",
                    }
                ]
            )

        if "chunk_type = 'article'" in sql and "law_code_normalized = :normalized_code" in sql:
            if self.raise_on_count:
                raise RuntimeError("DB unavailable")
            if self.empty_result:
                return _Result([])
            return _Result(
                [
                    {
                        "law_code_normalized": "45/2019/QH14",
                        "title": "Bộ luật Lao động",
                        "article_count": 220,
                    }
                ]
            )

        raise AssertionError(f"Unexpected SQL: {sql[:120]}")


def test_parse_catalog_request_extracts_law_code_from_natural_query() -> None:
    """Bug regression: parse_catalog_request phải extract law_code hoặc law_name_hint,
    không được trả về action='article_count' với cả hai là None khi câu hỏi có tên văn bản."""
    result = parse_catalog_request("Bộ luật Lao động 2019 có bao nhiêu Điều?")
    assert result is not None
    assert result.action == "article_count"
    # Phải extract được tên gợi ý (law_name_hint) vì không có mã số hình thức
    assert result.law_code is not None or result.law_name_hint is not None

    # Khi câu hỏi có mã số hình thức, phải extract law_code
    result2 = parse_catalog_request("Luật số 45/2019/QH14 có mấy điều?")
    assert result2 is not None
    assert result2.action == "article_count"
    assert result2.law_code is not None
    assert "45/2019" in result2.law_code

    # Câu không liên quan pháp luật không được match
    result3 = parse_catalog_request("Cháu có mấy điều muốn hỏi thầy?")
    assert result3 is None or result3.action != "article_count"


def test_article_count_sql_filters_by_law_code_and_returns_correct_count() -> None:
    """Bug regression: SQL phải có WHERE lc.law_code_normalized = :normalized_code
    và trả đúng 220 (không phải 3724 hay 404)."""
    db = _ArticleCountDB()
    service = LegalCatalogService(db)  # type: ignore[arg-type]

    answer = asyncio.run(
        service.answer(CatalogRequest(action="article_count", law_code="45/2019/QH14"))
    )

    # Kết quả phải chứa đúng 220
    assert "220" in answer
    # Không được chứa số sai cũ
    assert "3724" not in answer
    assert "404" not in answer

    # SQL được gọi phải có filter law_code_normalized
    count_sqls = [s for s in db.statements if "chunk_type = 'article'" in s]
    assert count_sqls, "Phải có SQL đếm article"
    assert any("law_code_normalized = :normalized_code" in s for s in count_sqls), (
        "SQL thiếu WHERE law_code_normalized = :normalized_code"
    )


def test_article_count_db_error_fallback_contains_no_hardcoded_number() -> None:
    """Bug regression: khi DB lỗi, fallback KHÔNG được trả số điều cụ thể (như 404).
    Chỉ được thông báo lỗi mà không đoán số."""
    import re as _re

    db = _ArticleCountDB(raise_on_count=True)
    service = LegalCatalogService(db)  # type: ignore[arg-type]

    answer = asyncio.run(
        service.answer(CatalogRequest(action="article_count", law_code="45/2019/QH14"))
    )

    # Không được chứa bất kỳ số lượng điều cụ thể nào
    assert not _re.search(r"\b\d{2,4}\s*[Đđ]iều\b", answer), (
        f"Fallback không được chứa số Điều cụ thể: {answer}"
    )
    # Phải nói rõ không thể xác định
    assert "tạm thời" in answer or "không thể" in answer or "thử lại" in answer


def test_article_count_unknown_law_returns_clarification() -> None:
    """Khi không extract được law_code hoặc name_hint, phải yêu cầu người dùng cung cấp mã số."""
    db = _ArticleCountDB()
    service = LegalCatalogService(db)  # type: ignore[arg-type]

    answer = asyncio.run(
        service.answer(CatalogRequest(action="article_count", law_code=None, law_name_hint=None))
    )

    # Phải hướng dẫn người dùng cung cấp mã số
    assert "mã số" in answer.lower() or "chưa xác định" in answer.lower() or "cung cấp" in answer.lower()
    # Không được trả số điều cụ thể
    assert "220" not in answer
    assert "404" not in answer
    assert "3724" not in answer

