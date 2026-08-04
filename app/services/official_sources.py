from __future__ import annotations

import re
from types import MappingProxyType


_OFFICIAL_LEGAL_SOURCE_URLS = MappingProxyType(
    {
        "161/2026/NĐ-CP": (
            "https://vanban.chinhphu.vn/"
            "?classid=1&docid=218107&orggroupid=2&pageid=27160"
        ),
        "162/2026/NĐ-CP": (
            "https://vanban.chinhphu.vn/"
            "?classid=1&docid=218110&pageid=27160&typegroupid=4"
        ),
    }
)


def normalize_official_document_code(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def official_legal_source_url(code: str | None) -> str | None:
    """Return a verified, direct official URL for bundled corpus documents.

    This registry only contains exact document pages that have been verified.
    Unknown codes deliberately return ``None`` instead of producing a search
    URL or an internal document route that could be mistaken for the source.
    """

    return _OFFICIAL_LEGAL_SOURCE_URLS.get(
        normalize_official_document_code(code)
    )
