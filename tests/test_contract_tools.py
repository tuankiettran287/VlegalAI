from __future__ import annotations

import asyncio
import io
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from docx import Document

from app.api import compare_contracts, draft_contract
from app.schemas import (
    CompareContractRequest,
    DraftContractRequest,
    VerificationItem,
    VerificationReport,
)
from app.services.contract_analysis import (
    build_contract_diff,
    contract_retrieval_query,
    looks_like_contract,
)
from app.services.contract_documents import (
    MAX_DOCUMENT_BYTES,
    ContractDocumentError,
    extract_contract_document,
)


def test_extract_contract_document_supports_utf8_and_docx_tables() -> None:
    plain = extract_contract_document(
        "HỢP ĐỒNG DỊCH VỤ\n\nĐiều 1. Phạm vi công việc".encode(),
        "hop-dong.txt",
    )
    assert plain.text.startswith("HỢP ĐỒNG DỊCH VỤ")
    assert plain.truncated is False

    document = Document()
    document.add_heading("HỢP ĐỒNG DỊCH VỤ", level=1)
    document.add_paragraph("Điều 1. Phạm vi công việc")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Thời hạn"
    table.cell(0, 1).text = "12 tháng"
    output = io.BytesIO()
    document.save(output)

    extracted = extract_contract_document(output.getvalue(), "hop-dong.docx")
    assert "Điều 1. Phạm vi công việc" in extracted.text
    assert "Thời hạn | 12 tháng" in extracted.text


def test_extract_contract_document_rejects_unsupported_and_oversized_files() -> None:
    with pytest.raises(ContractDocumentError, match="Chỉ hỗ trợ"):
        extract_contract_document(b"not a contract", "contract.exe")
    with pytest.raises(ContractDocumentError, match="15 MB"):
        extract_contract_document(b"x" * (MAX_DOCUMENT_BYTES + 1), "contract.txt")


def test_contract_detection_and_retrieval_query_use_structure_not_full_body() -> None:
    short_request = "Soạn hợp đồng dịch vụ phát triển phần mềm."
    assert looks_like_contract(short_request) is False

    source = (
        "HỢP ĐỒNG DỊCH VỤ\n\n"
        "Điều 1. Phạm vi\nNội dung có thông tin riêng tư không được đưa vào truy vấn. " * 30
        + "\nĐiều 2. Thanh toán"
    )
    assert looks_like_contract(source) is True
    query = contract_retrieval_query("Rà soát hợp đồng", source)
    assert "Điều 1. Phạm vi" in query
    assert "thông tin riêng tư" not in query
    assert len(query) <= 1_600


def test_contract_diff_detects_added_deleted_and_modified_groups() -> None:
    original = "Điều 1. Phạm vi\n\nĐiều 2. Giá trị: 10 triệu\n\nĐiều 3. Bảo mật"
    revised = "Điều 1. Phạm vi\n\nĐiều 2. Giá trị: 12 triệu\n\nĐiều 4. Chấm dứt"
    result = build_contract_diff(original, revised)
    assert result["similarity"] < 100
    assert result["counts"]["modified"] >= 1
    assert result["changes"]


class _ArtifactDb:
    def __init__(self, user_id: uuid.UUID) -> None:
        self.user_id = user_id
        self.added: list[object] = []

    async def rollback(self) -> None:
        return None

    async def scalar(self, _: object) -> object:
        return self.user_id

    def add(self, value: object) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        return None

    async def refresh(self, value: object) -> None:
        if getattr(value, "id", None) is None:
            value.id = uuid.uuid4()


class _FastContractRetrieval:
    def __init__(self) -> None:
        self.queries: list[str] = []

    async def retrieve(self, query: str) -> list[dict[str, object]]:
        self.queries.append(query)
        return [{
            "source_id": "S1",
            "doc_id": "law-1",
            "title": "Luật thử nghiệm",
            "citation": "100/2020/QH14",
            "text": "Nội dung pháp lý đã được kiểm chứng.",
        }]


class _Freshness:
    settings = SimpleNamespace(
        max_laws_verified_per_request=16,
        require_freshness_check=True,
    )

    async def verify_sources(
        self,
        _: list[dict[str, object]],
    ) -> tuple[VerificationReport, bool]:
        checked_at = datetime.now(UTC)
        return VerificationReport(
            checked=True,
            all_current=True,
            checked_at=checked_at,
            items=[
                VerificationItem(
                    code="100/2020/QH14",
                    title="Luật thử nghiệm",
                    status="IN_FORCE",
                    checked_at=checked_at,
                )
            ],
        ), False


def test_draft_accepts_full_contract_without_graph_route_or_mandatory_inline_citations() -> None:
    user_id = uuid.uuid4()
    db = _ArtifactDb(user_id)
    retrieval = _FastContractRetrieval()
    full_contract = (
        "HỢP ĐỒNG DỊCH VỤ\n\nĐiều 1. Phạm vi\n"
        + ("Nội dung hợp đồng hiện có. " * 60)
        + "\n\nĐiều 2. Thanh toán"
    )

    class _Ai:
        async def complete(self, *_: object, **__: object) -> str:
            return "HỢP ĐỒNG DỊCH VỤ\n\nĐiều 1. Phạm vi đã được hoàn thiện."

    result = asyncio.run(
        draft_contract(
            DraftContractRequest(prompt=full_contract, template_name="Hợp đồng dịch vụ"),
            db,
            SimpleNamespace(id=user_id),
            SimpleNamespace(
                gemini_model="gemini-2.5-flash",
                message_encryption_key="",
                session_secret="test-session-secret-at-least-32-bytes",
            ),
            retrieval,
            _Freshness(),
            _Ai(),
        )
    )
    assert result["draft"].startswith("HỢP ĐỒNG")
    assert len(retrieval.queries[0]) <= 1_600


def test_identical_contracts_skip_retrieval_and_ai() -> None:
    user_id = uuid.uuid4()
    db = _ArtifactDb(user_id)

    class _MustNotRun:
        def __getattr__(self, name: str) -> object:
            raise AssertionError(f"{name} must not run for identical contracts")

    result = asyncio.run(
        compare_contracts(
            CompareContractRequest(
                original_text="Điều 1. Nội dung hợp đồng giống nhau.",
                revised_text="Điều 1. Nội dung hợp đồng giống nhau.",
            ),
            db,
            SimpleNamespace(id=user_id),
            SimpleNamespace(
                gemini_model="gemini-2.5-flash",
                message_encryption_key="",
                session_secret="test-session-secret-at-least-32-bytes",
            ),
            _MustNotRun(),
            _MustNotRun(),
            _MustNotRun(),
        )
    )
    assert result["similarity"] == 100
    assert result["differences"] == []
    assert result["sources"] == []
