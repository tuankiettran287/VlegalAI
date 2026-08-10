from app.services.official_sources import official_legal_source_url


def test_official_source_registry_normalizes_document_code() -> None:
    assert official_legal_source_url(" 161 / 2026 / nđ-cp ") == (
        "https://vanban.chinhphu.vn/"
        "?classid=1&docid=218107&orggroupid=2&pageid=27160"
    )


def test_official_source_registry_contains_labor_code() -> None:
    assert official_legal_source_url("45/2019/QH14") == (
        "https://vanban.chinhphu.vn/"
        "?docid=198540&lang=vi&pageid=27160"
    )


def test_official_source_registry_does_not_guess_unknown_documents() -> None:
    assert official_legal_source_url("999/2099/NĐ-CP") is None
