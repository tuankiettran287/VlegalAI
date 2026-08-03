import asyncio
from typing import Any

import pytest
from fastapi import HTTPException

from app.api import law_detail


class _MappingResult:
    def __init__(self, *, first: dict[str, Any] | None = None, rows: list[dict[str, Any]] | None = None):
        self._first = first
        self._rows = rows or []

    def mappings(self) -> "_MappingResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._first

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _DetailDb:
    def __init__(self, *, metadata: dict[str, Any] | None, sections: list[dict[str, Any]] | None = None):
        self.metadata = metadata
        self.sections = sections or []
        self.execute_calls = 0

    async def execute(self, statement: Any, params: dict[str, Any]) -> _MappingResult:
        self.execute_calls += 1
        if self.execute_calls == 1:
            return _MappingResult(first=self.metadata)
        assert ":code" in str(statement)
        assert params["code"] == "45/2019/QH14"
        return _MappingResult(rows=self.sections)

    async def scalar(self, statement: Any, params: dict[str, Any]) -> int:
        assert ":code" in str(statement)
        assert params["citation"] == "Bộ luật Lao động (45/2019/QH14) > Điều 91"
        return len(self.sections)


def test_law_detail_returns_the_exact_indexed_citation() -> None:
    db = _DetailDb(
        metadata={
            "code": "45/2019/QH14",
            "title": "Bộ luật Lao động",
            "document_type": "CODE",
            "issuer": "Quốc hội",
            "source_url": "https://vanban.chinhphu.vn/?pageid=27160&docid=198540",
            "status": "IN_FORCE",
            "law_version": 1,
        },
        sections=[
            {
                "citation": "Bộ luật Lao động (45/2019/QH14) > Điều 91",
                "title": "Điều 91. Mức lương tối thiểu",
                "path_label": "Chương VI > Điều 91",
                "text": "Mức lương tối thiểu là mức lương thấp nhất...",
                "chunk_type": "article",
                "ordinal": 90,
            }
        ],
    )

    result = asyncio.run(
        law_detail(
            code="45/2019/QH14",
            citation="Bộ luật Lao động (45/2019/QH14) > Điều 91",
            page=1,
            page_size=50,
            db=db,  # type: ignore[arg-type]
            _=object(),  # type: ignore[arg-type]
        )
    )

    assert result.code == "45/2019/QH14"
    assert result.focused is True
    assert result.sections[0].ordinal == 90
    assert result.source_url and "docid=198540" in result.source_url


def test_law_detail_returns_404_for_unknown_document() -> None:
    db = _DetailDb(metadata=None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            law_detail(
                code="999/2099/QH99",
                citation="",
                page=1,
                page_size=50,
                db=db,  # type: ignore[arg-type]
                _=object(),  # type: ignore[arg-type]
            )
        )

    assert exc_info.value.status_code == 404
