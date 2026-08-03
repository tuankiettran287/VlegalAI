from app.schemas import SourceOut


def test_source_without_direct_url_gets_internal_document_code() -> None:
    source = SourceOut(
        source_id="S1",
        citation=(
            "Nghị định quy định mức lương cơ sở "
            "(161/2026/NĐ-CP) > Điều 3"
        ),
    )

    assert source.document_code == "161/2026/NĐ-CP"
    assert source.source_url is None


def test_direct_source_url_takes_priority_over_lookup_link() -> None:
    source = SourceOut(
        source_id="S1",
        citation="Bộ luật Lao động (45/2019/QH14)",
        source_url="https://vanban.chinhphu.vn/?docid=198540&pageid=27160",
    )

    assert source.source_url == (
        "https://vanban.chinhphu.vn/?docid=198540&pageid=27160"
    )
    assert source.document_code == "45/2019/QH14"


def test_consolidated_document_code_is_supported() -> None:
    source = SourceOut(
        source_id="S1",
        citation="Văn bản hợp nhất số 22/VBHN-BTC > Điều 4",
    )

    assert source.document_code == "22/VBHN-BTC"


def test_non_legal_attachment_does_not_get_external_lookup_link() -> None:
    source = SourceOut(
        source_id="S1",
        citation="Tệp người dùng cung cấp: hop-dong.docx",
    )

    assert source.document_code is None
