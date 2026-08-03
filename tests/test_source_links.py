from urllib.parse import parse_qs, urlparse

from app.schemas import SourceOut


def test_source_without_direct_url_gets_official_lookup_link() -> None:
    source = SourceOut(
        source_id="S1",
        citation=(
            "Nghị định quy định mức lương cơ sở "
            "(161/2026/NĐ-CP) > Điều 3"
        ),
    )

    assert source.lookup_url is not None
    parsed = urlparse(source.lookup_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "vanban.chinhphu.vn"
    assert parse_qs(parsed.query) == {
        "pageid": ["473"],
        "q": ["161/2026/NĐ-CP"],
    }


def test_direct_source_url_takes_priority_over_lookup_link() -> None:
    source = SourceOut(
        source_id="S1",
        citation="Bộ luật Lao động (45/2019/QH14)",
        source_url="https://vanban.chinhphu.vn/?docid=198540&pageid=27160",
    )

    assert source.source_url == (
        "https://vanban.chinhphu.vn/?docid=198540&pageid=27160"
    )
    assert source.lookup_url is None


def test_non_legal_attachment_does_not_get_external_lookup_link() -> None:
    source = SourceOut(
        source_id="S1",
        citation="Tệp người dùng cung cấp: hop-dong.docx",
    )

    assert source.lookup_url is None
