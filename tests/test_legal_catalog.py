from __future__ import annotations

import pytest

from app.services.legal_catalog import CatalogRequest, parse_catalog_request


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "Kho VLegal có bao nhiêu nghị định đang còn hiệu lực?",
            CatalogRequest(action="count", document_type="DECREE", status="CURRENT"),
        ),
        (
            "Trong kho dữ liệu VLegal có bao nhiêu thông tư hết hiệu lực?",
            CatalogRequest(action="count", document_type="CIRCULAR", status="EXPIRED"),
        ),
        (
            "Hệ thống VLegal có bao nhiêu bộ luật?",
            CatalogRequest(action="count", document_type="CODE"),
        ),
        (
            "Cơ sở dữ liệu pháp lý VLegal có bao nhiêu luật?",
            CatalogRequest(action="count", document_type="LAW"),
        ),
        (
            "Kho VLegal có bao nhiêu văn bản hợp nhất?",
            CatalogRequest(action="count", document_type="CONSOLIDATED"),
        ),
        (
            "Trong hệ thống VLegal có bao nhiêu nghị quyết?",
            CatalogRequest(action="count", document_type="RESOLUTION"),
        ),
        (
            "Kho văn bản VLegal có bao nhiêu quyết định?",
            CatalogRequest(action="count", document_type="DECISION"),
        ),
        (
            "Liệt kê các thông tư đang có trong kho VLegal",
            CatalogRequest(action="list", document_type="CIRCULAR"),
        ),
        (
            "Danh sách nghị định còn hiệu lực trong hệ thống VLegal",
            CatalogRequest(action="list", document_type="DECREE", status="CURRENT"),
        ),
        (
            "Kho VLegal gồm những bộ luật nào?",
            CatalogRequest(action="list", document_type="CODE"),
        ),
        (
            "VLegal đang có những luật nào đã hết hiệu lực?",
            CatalogRequest(action="list", document_type="LAW", status="EXPIRED"),
        ),
        (
            "Thống kê kho văn bản VLegal",
            CatalogRequest(action="summary"),
        ),
        (
            "Cho tôi thông tin tổng quan về dữ liệu của VLegal",
            CatalogRequest(action="summary"),
        ),
        (
            "Phân bố các loại văn bản trong hệ thống VLegal",
            CatalogRequest(action="summary"),
        ),
        (
            "Danh mục văn bản pháp luật",
            CatalogRequest(action="list", document_type="LAW"),
        ),
        (
            "Liệt kê các loại văn bản",
            CatalogRequest(action="list"),
        ),
    ],
)
def test_parse_catalog_request_recognizes_scoped_catalog_questions(
    query: str,
    expected: CatalogRequest,
) -> None:
    assert parse_catalog_request(query) == expected


@pytest.mark.parametrize(
    "query",
    [
        "Cơ sở dữ liệu pháp luật chính thức có bao nhiêu văn bản?",
        "Toàn bộ hệ thống pháp luật Việt Nam có bao nhiêu luật?",
        "Tất cả văn bản hiện hành có bao nhiêu nghị định?",
        "Trên toàn quốc có bao nhiêu thông tư đang còn hiệu lực?",
    ],
)
def test_parse_catalog_request_declines_nationwide_official_catalog_claims(
    query: str,
) -> None:
    assert parse_catalog_request(query) == CatalogRequest(
        action="unsupported_official_catalog"
    )


@pytest.mark.parametrize(
    "query",
    [
        "Có bao nhiêu điều luật?",
        "Một bộ luật có mấy điều luật?",
    ],
)
def test_parse_catalog_request_requires_scope_for_ambiguous_article_counts(
    query: str,
) -> None:
    assert parse_catalog_request(query) == CatalogRequest(action="scope_required")


@pytest.mark.parametrize(
    ("query", "law_code", "law_name_hint"),
    [
        ("Luật 45/2019/QH14 có bao nhiêu Điều?", "45/2019/QH14", None),
        ("45/2019/QH14 gồm mấy điều?", "45/2019/QH14", None),
        ("Nghị định 145/2020/NĐ-CP có bao nhiêu điều?", "145/2020/NĐ-CP", None),
        ("Thông tư 10/2022/TT-BLĐTBXH gồm bao nhiêu Điều?", "10/2022/TT-BLĐTBXH", None),
        ("Bộ luật lao động 2019 có bao nhiêu điều?", None, "bo luat lao dong 2019"),
        ("Bộ luật lao động gồm mấy điều?", None, "bo luat lao dong"),
        ("Luật doanh nghiệp 2020 có bao nhiêu điều?", None, "luat doanh nghiep 2020"),
        ("Nghị định về lao động có bao nhiêu điều?", None, "nghi dinh ve lao dong"),
    ],
)
def test_parse_catalog_request_extracts_specific_document_for_article_count(
    query: str,
    law_code: str | None,
    law_name_hint: str | None,
) -> None:
    assert parse_catalog_request(query) == CatalogRequest(
        action="article_count",
        law_code=law_code,
        law_name_hint=law_name_hint,
    )


@pytest.mark.parametrize(
    "query",
    [
        "Cháu có mấy điều muốn hỏi luật sư.",
        "Tôi có bao nhiêu ngày phép năm?",
        "Công ty có bao nhiêu nhân viên?",
        "Luật lao động quy định về trợ cấp thôi việc thế nào?",
        "Nghị định mới nhất về lương tối thiểu là gì?",
        "Liệt kê quyền của người lao động khi nghỉ việc.",
        "Thống kê chi phí nhân sự quý này.",
        "Cho tôi danh sách giấy tờ cần chuẩn bị.",
        "Trong hợp đồng có những điều khoản nào bất lợi?",
        "Hệ thống có đang hoạt động không?",
    ],
)
def test_parse_catalog_request_does_not_hijack_normal_legal_questions(query: str) -> None:
    assert parse_catalog_request(query) is None


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (
            "  KHO   VLEGAL  CÓ  BAO  NHIÊU  NGHỊ  ĐỊNH?  ",
            CatalogRequest(action="count", document_type="DECREE"),
        ),
        (
            "kho vlegal co bao nhieu nghi dinh dang con hieu luc",
            CatalogRequest(action="count", document_type="DECREE", status="CURRENT"),
        ),
        (
            "DANH SÁCH   THÔNG TƯ  TRONG  HỆ THỐNG VLEGAL",
            CatalogRequest(action="list", document_type="CIRCULAR"),
        ),
        (
            "thong ke du lieu cua vlegal",
            CatalogRequest(action="summary"),
        ),
    ],
)
def test_parse_catalog_request_is_stable_across_case_accents_and_whitespace(
    query: str,
    expected: CatalogRequest,
) -> None:
    assert parse_catalog_request(query) == expected
