from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from docx import Document
from pypdf import PdfReader

MAX_DOCUMENT_BYTES = 15 * 1024 * 1024
MAX_EXTRACTED_CHARS = 120_000
MAX_PDF_PAGES = 250
MAX_DOCX_ENTRIES = 5_000
MAX_DOCX_UNCOMPRESSED_BYTES = 40 * 1024 * 1024
SUPPORTED_DOCUMENT_EXTENSIONS = {".docx", ".md", ".pdf", ".txt"}


class ContractDocumentError(ValueError):
    """Raised when an uploaded contract cannot be read safely."""


@dataclass(frozen=True, slots=True)
class ExtractedContractDocument:
    filename: str
    text: str
    original_chars: int
    truncated: bool
    page_count: int | None = None


def _normalize_text(value: str) -> str:
    normalized = value.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.splitlines())
    return re.sub(r"\n{4,}", "\n\n\n", normalized).strip()


def _bounded_text(value: str, filename: str, page_count: int | None = None) -> ExtractedContractDocument:
    normalized = _normalize_text(value)
    if len(normalized) < 20:
        raise ContractDocumentError(
            "Không đọc được nội dung văn bản. Nếu đây là bản scan, hãy dùng file PDF có lớp chữ hoặc DOCX."
        )
    original_chars = len(normalized)
    return ExtractedContractDocument(
        filename=filename,
        text=normalized[:MAX_EXTRACTED_CHARS],
        original_chars=original_chars,
        truncated=original_chars > MAX_EXTRACTED_CHARS,
        page_count=page_count,
    )


def _decode_plain_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1258"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ContractDocumentError("File văn bản phải dùng bảng mã UTF-8, UTF-16 hoặc tiếng Việt Windows.")


def _extract_docx(data: bytes) -> tuple[str, None]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if (
                len(entries) > MAX_DOCX_ENTRIES
                or sum(entry.file_size for entry in entries) > MAX_DOCX_UNCOMPRESSED_BYTES
            ):
                raise ContractDocumentError("File DOCX vượt quá giới hạn giải nén an toàn.")
    except zipfile.BadZipFile as exc:
        raise ContractDocumentError("File DOCX không hợp lệ hoặc đã bị hỏng.") from exc

    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:
        raise ContractDocumentError("Không thể đọc file DOCX này.") from exc

    blocks: list[str] = []
    blocks.extend(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                blocks.append(" | ".join(cells))
    return "\n\n".join(blocks), None


def _extract_pdf(data: bytes) -> tuple[str, int]:
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ContractDocumentError("File PDF không hợp lệ hoặc đã bị hỏng.") from exc
    if reader.is_encrypted:
        raise ContractDocumentError("Không hỗ trợ PDF đang được đặt mật khẩu.")
    page_count = len(reader.pages)
    if page_count > MAX_PDF_PAGES:
        raise ContractDocumentError(f"PDF chỉ được tối đa {MAX_PDF_PAGES} trang.")

    pages: list[str] = []
    try:
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                pages.append(text)
            if sum(len(item) for item in pages) > MAX_EXTRACTED_CHARS:
                break
    except Exception as exc:
        raise ContractDocumentError("Không thể trích xuất chữ từ PDF này.") from exc
    return "\n\n".join(pages), page_count


def extract_contract_document(
    data: bytes,
    filename: str,
    content_type: str | None = None,
) -> ExtractedContractDocument:
    if not data:
        raise ContractDocumentError("File tải lên đang trống.")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ContractDocumentError("File hợp đồng chỉ được tối đa 15 MB.")

    safe_filename = Path(filename or "hop-dong").name[:255]
    extension = Path(safe_filename).suffix.casefold()
    if extension not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise ContractDocumentError("Chỉ hỗ trợ file PDF, DOCX, TXT hoặc Markdown.")

    if extension in {".txt", ".md"}:
        text, page_count = _decode_plain_text(data), None
    elif extension == ".docx":
        text, page_count = _extract_docx(data)
    else:
        text, page_count = _extract_pdf(data)
    return _bounded_text(text, safe_filename, page_count)
