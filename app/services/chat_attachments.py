from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from app.core.config import Settings
from app.core.security import decrypt_text, encrypt_text
from app.services.contract_documents import (
    ContractDocumentError,
    extract_contract_document,
)

MAX_CHAT_ATTACHMENTS = 3
MAX_CHAT_ATTACHMENT_BYTES = 15 * 1024 * 1024
MAX_ATTACHMENT_TEXT_CHARS = 50_000
MAX_COMBINED_ATTACHMENT_TEXT_CHARS = 80_000
ATTACHMENT_TOKEN_TTL_MINUTES = 30

_ATTACHMENT_FACT_TERMS = {
    "ai",
    "bao nhieu",
    "ben nao",
    "chuc danh",
    "cong viec",
    "dia chi",
    "dia diem",
    "ghi gi",
    "gia tri",
    "ke tu ngay",
    "luong",
    "muc luong",
    "ngay bat dau",
    "ngay ket thuc",
    "ngay ky",
    "noi dung",
    "quy dinh gi",
    "so tien",
    "ten gi",
    "thoi han",
    "tien luong",
    "tom tat",
    "trich",
}
_ATTACHMENT_REFERENCE_TERMS = {
    "anh nay",
    "file nay",
    "hop dong",
    "noi dung tren",
    "tai lieu",
    "tep dinh kem",
    "tep nay",
    "van ban nay",
}
_LEGAL_ANALYSIS_TERMS = {
    "bat loi",
    "boi thuong",
    "co dung luat",
    "co hop phap",
    "co phu hop",
    "danh gia phap ly",
    "dung phap luat",
    "hieu luc phap ly",
    "khoi kien",
    "phan tich phap ly",
    "ra soat rui ro",
    "review",
    "theo phap luat",
    "theo quy dinh phap luat",
    "trai luat",
    "vi pham phap luat",
}
_ATTACHMENT_QUERY_STOPWORDS = {
    "anh",
    "ban",
    "cua",
    "cho",
    "co",
    "duoc",
    "gi",
    "hay",
    "hop",
    "la",
    "mot",
    "nay",
    "noi",
    "toi",
    "trong",
    "ve",
    "voi",
}
_ATTACHMENT_TERM_EXPANSIONS = {
    "luong": {"luong", "muc luong", "tien luong", "thu nhap", "vnd"},
    "tien": {"so tien", "muc luong", "tien luong", "vnd"},
    "thoi han": {"thoi han", "ke tu ngay", "den ngay", "thang", "nam"},
    "ngay": {"ngay ky", "ngay bat dau", "ngay ket thuc", "ke tu ngay"},
    "cong viec": {"cong viec", "chuc danh", "vi tri", "nhiem vu"},
    "dia diem": {"dia diem", "noi lam viec", "dia chi"},
}


def _normalize_attachment_text(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    without_marks = "".join(
        "d" if character in {"Đ", "đ"} else character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    return (
        re.sub(r"\s+", " ", re.sub(r"[^0-9a-zA-Z]+", " ", without_marks))
        .strip()
        .casefold()
    )


def is_direct_attachment_question(question: str) -> bool:
    """Return true when the user asks for facts stated inside an uploaded file.

    Requests to assess legality or risk stay on the hybrid document + law path.
    """

    normalized = _normalize_attachment_text(question)
    if not normalized or any(term in normalized for term in _LEGAL_ANALYSIS_TERMS):
        return False
    references_attachment = any(
        term in normalized for term in _ATTACHMENT_REFERENCE_TERMS
    )
    asks_for_fact = any(term in normalized for term in _ATTACHMENT_FACT_TERMS)
    return asks_for_fact or references_attachment


def _attachment_query_terms(question: str) -> set[str]:
    normalized = _normalize_attachment_text(question)
    terms = {
        token
        for token in re.findall(r"[0-9a-z]+", normalized)
        if len(token) >= 2 and token not in _ATTACHMENT_QUERY_STOPWORDS
    }
    phrases = {
        phrase
        for phrase in (*_ATTACHMENT_FACT_TERMS, *_ATTACHMENT_REFERENCE_TERMS)
        if phrase in normalized
    }
    terms.update(phrases)
    for trigger, expansions in _ATTACHMENT_TERM_EXPANSIONS.items():
        if trigger in normalized:
            terms.update(expansions)
    return terms


def _attachment_segments(text: str, *, segment_chars: int = 900) -> list[str]:
    paragraphs = [
        line.strip()
        for line in text.replace("\x00", "").replace("\r\n", "\n").splitlines()
        if line.strip()
    ]
    segments: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= segment_chars:
            segments.append(paragraph)
            continue
        sentences = re.split(r"(?<=[.!?;:])\s+", paragraph)
        buffer = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if buffer and len(buffer) + 1 + len(sentence) > segment_chars:
                segments.append(buffer)
                buffer = ""
            if len(sentence) > segment_chars:
                if buffer:
                    segments.append(buffer)
                    buffer = ""
                segments.extend(
                    sentence[start : start + segment_chars]
                    for start in range(0, len(sentence), segment_chars)
                )
            else:
                buffer = f"{buffer} {sentence}".strip()
        if buffer:
            segments.append(buffer)
    return segments


def select_relevant_attachment_context(
    payloads: list[dict[str, Any]],
    question: str,
    *,
    max_chars: int = 12_000,
    per_file_chars: int = 7_000,
) -> list[dict[str, Any]]:
    """Select query-relevant excerpts while preserving file metadata.

    Matching segments include adjacent lines so labels, values and units remain
    together even when the source DOCX/PDF extractor emitted them separately.
    """

    query_terms = _attachment_query_terms(question)
    normalized_question = _normalize_attachment_text(question)
    summary_request = any(
        term in normalized_question
        for term in {"tom tat", "noi dung chinh", "tong quan", "doc tai lieu"}
    )
    selected_payloads: list[dict[str, Any]] = []
    remaining_total = max(0, max_chars)

    for payload in payloads:
        if remaining_total <= 0:
            break
        text = str(payload.get("text") or "").strip()
        segments = _attachment_segments(text)
        if not segments:
            continue
        file_budget = min(per_file_chars, remaining_total)

        if summary_request:
            candidate_indexes = list(range(len(segments)))
        else:
            scored: list[tuple[float, int]] = []
            for index, segment in enumerate(segments):
                normalized_segment = _normalize_attachment_text(segment)
                score = 0.0
                for term in query_terms:
                    normalized_term = _normalize_attachment_text(term)
                    if not normalized_term:
                        continue
                    if " " in normalized_term:
                        matched = normalized_term in normalized_segment
                    else:
                        matched = re.search(
                            rf"\b{re.escape(normalized_term)}\b",
                            normalized_segment,
                        ) is not None
                    if not matched:
                        continue
                    score += 4.0 if " " in normalized_term else 1.5
                if re.search(r"\b\d[\d.,/\-]*\b", normalized_segment):
                    score += 0.5
                if score:
                    scored.append((score, index))
            scored.sort(key=lambda item: (-item[0], item[1]))
            anchors = [index for _, index in scored[:8]]
            candidate_indexes = sorted(
                {
                    neighbor
                    for index in anchors
                    for neighbor in range(
                        max(0, index - 2),
                        min(len(segments), index + 3),
                    )
                }
            )
            if not candidate_indexes:
                candidate_indexes = list(range(min(6, len(segments))))

        excerpts: list[str] = []
        used = 0
        for index in candidate_indexes:
            segment = segments[index]
            addition = len(segment) + (1 if excerpts else 0)
            if used + addition > file_budget:
                remaining_file = file_budget - used
                if remaining_file >= 120:
                    excerpts.append(segment[:remaining_file].rstrip())
                break
            excerpts.append(segment)
            used += addition
        excerpt = "\n".join(excerpts).strip()
        if not excerpt:
            continue
        selected_payloads.append({**payload, "text": excerpt})
        remaining_total -= len(excerpt)

    return selected_payloads

IMAGE_MIME_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
DOCUMENT_MIME_BY_EXTENSION = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


class ChatAttachmentError(ValueError):
    """Raised when a chat attachment cannot be accepted safely."""


@dataclass(frozen=True, slots=True)
class ValidatedChatAttachment:
    filename: str
    content_type: str
    kind: Literal["image", "document"]
    size_bytes: int
    data: bytes
    requires_ocr: bool


@dataclass(frozen=True, slots=True)
class ExtractedChatAttachment:
    filename: str
    content_type: str
    kind: Literal["image", "document"]
    size_bytes: int
    text: str
    truncated: bool
    page_count: int | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "content_type": self.content_type,
            "kind": self.kind,
            "size_bytes": self.size_bytes,
            "page_count": self.page_count,
            "truncated": self.truncated,
        }

    def token_payload(self, user_id: str) -> dict[str, Any]:
        return {
            "version": 1,
            "user_id": user_id,
            "expires_at": (
                datetime.now(UTC) + timedelta(minutes=ATTACHMENT_TOKEN_TTL_MINUTES)
            ).isoformat(),
            **self.metadata(),
            "text": self.text,
        }


def _has_valid_image_signature(data: bytes, content_type: str) -> bool:
    if content_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def validate_chat_attachment(
    data: bytes,
    filename: str,
    content_type: str | None = None,
) -> ValidatedChatAttachment:
    del content_type  # Never trust the browser-provided MIME type.
    if not data:
        raise ChatAttachmentError("Tệp đính kèm đang trống.")
    if len(data) > MAX_CHAT_ATTACHMENT_BYTES:
        raise ChatAttachmentError("Mỗi tệp đính kèm chỉ được tối đa 15 MB.")

    safe_filename = Path(filename or "tep-dinh-kem").name[:255]
    extension = Path(safe_filename).suffix.casefold()
    if extension in IMAGE_MIME_BY_EXTENSION:
        normalized_type = IMAGE_MIME_BY_EXTENSION[extension]
        if not _has_valid_image_signature(data, normalized_type):
            raise ChatAttachmentError(
                "Nội dung ảnh không khớp với định dạng JPEG, PNG hoặc WebP."
            )
        return ValidatedChatAttachment(
            filename=safe_filename,
            content_type=normalized_type,
            kind="image",
            size_bytes=len(data),
            data=data,
            requires_ocr=True,
        )

    if extension not in DOCUMENT_MIME_BY_EXTENSION:
        raise ChatAttachmentError(
            "Chỉ hỗ trợ ảnh JPEG, PNG, WebP hoặc tài liệu PDF, DOCX, TXT, Markdown."
        )
    if extension == ".pdf" and not data.startswith(b"%PDF"):
        raise ChatAttachmentError("File PDF không hợp lệ hoặc đã bị hỏng.")
    return ValidatedChatAttachment(
        filename=safe_filename,
        content_type=DOCUMENT_MIME_BY_EXTENSION[extension],
        kind="document",
        size_bytes=len(data),
        data=data,
        requires_ocr=False,
    )


def extract_document_attachment(
    attachment: ValidatedChatAttachment,
) -> ExtractedChatAttachment:
    if attachment.kind != "document":
        raise ChatAttachmentError("Ảnh cần được xử lý bằng OCR.")
    try:
        extracted = extract_contract_document(
            attachment.data,
            attachment.filename,
            attachment.content_type,
        )
    except ContractDocumentError as exc:
        raise ChatAttachmentError(str(exc)) from exc
    text = extracted.text[:MAX_ATTACHMENT_TEXT_CHARS]
    return ExtractedChatAttachment(
        filename=attachment.filename,
        content_type=attachment.content_type,
        kind=attachment.kind,
        size_bytes=attachment.size_bytes,
        text=text,
        truncated=extracted.truncated or len(extracted.text) > len(text),
        page_count=extracted.page_count,
    )


def extracted_ocr_attachment(
    attachment: ValidatedChatAttachment,
    text: str,
) -> ExtractedChatAttachment:
    normalized = "\n".join(
        line.rstrip()
        for line in text.replace("\x00", "").replace("\r\n", "\n").splitlines()
    ).strip()
    if len(normalized) < 10:
        raise ChatAttachmentError(
            "Không đọc được nội dung từ ảnh hoặc tài liệu scan này."
        )
    bounded = normalized[:MAX_ATTACHMENT_TEXT_CHARS]
    return ExtractedChatAttachment(
        filename=attachment.filename,
        content_type=attachment.content_type,
        kind=attachment.kind,
        size_bytes=attachment.size_bytes,
        text=bounded,
        truncated=len(normalized) > len(bounded),
    )


def create_attachment_token(
    attachment: ExtractedChatAttachment,
    user_id: str,
    settings: Settings,
) -> str:
    return encrypt_text(
        json.dumps(
            attachment.token_payload(user_id),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        settings,
    )


def decode_attachment_token(
    token: str,
    user_id: str,
    settings: Settings,
) -> dict[str, Any]:
    try:
        payload = json.loads(decrypt_text(token, settings))
        expires_at = datetime.fromisoformat(str(payload["expires_at"]))
    except Exception as exc:
        raise ChatAttachmentError(
            "Tệp đính kèm không hợp lệ; vui lòng tải lên lại."
        ) from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ChatAttachmentError("Phiên bản tệp đính kèm không được hỗ trợ.")
    if str(payload.get("user_id")) != str(user_id):
        raise ChatAttachmentError("Tệp đính kèm không thuộc tài khoản hiện tại.")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise ChatAttachmentError("Tệp đính kèm đã hết hạn; vui lòng tải lên lại.")

    text = str(payload.get("text") or "").strip()
    kind = str(payload.get("kind") or "")
    if not text or kind not in {"image", "document"}:
        raise ChatAttachmentError("Tệp đính kèm không có nội dung có thể sử dụng.")
    payload["text"] = text[:MAX_ATTACHMENT_TEXT_CHARS]
    payload["filename"] = Path(str(payload.get("filename") or "tệp đính kèm")).name[:255]
    payload["content_type"] = str(payload.get("content_type") or "application/octet-stream")[:120]
    payload["kind"] = kind
    payload["size_bytes"] = max(0, int(payload.get("size_bytes") or 0))
    payload["page_count"] = (
        max(0, int(payload["page_count"]))
        if payload.get("page_count") is not None
        else None
    )
    payload["truncated"] = bool(payload.get("truncated"))
    return payload


def attachment_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "filename": payload["filename"],
        "content_type": payload["content_type"],
        "kind": payload["kind"],
        "size_bytes": payload["size_bytes"],
        "page_count": payload.get("page_count"),
        "truncated": bool(payload.get("truncated")),
    }


def serialize_attachment_context(payloads: list[dict[str, Any]]) -> str:
    return json.dumps(
        [
            {
                **attachment_metadata(payload),
                "text": str(payload.get("text") or "")[:MAX_ATTACHMENT_TEXT_CHARS],
            }
            for payload in payloads
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def deserialize_attachment_context(value: str) -> list[dict[str, Any]]:
    try:
        payloads = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(payloads, list):
        return []
    result: list[dict[str, Any]] = []
    total_chars = 0
    for payload in payloads[:MAX_CHAT_ATTACHMENTS]:
        if not isinstance(payload, dict):
            continue
        text = str(payload.get("text") or "").strip()[:MAX_ATTACHMENT_TEXT_CHARS]
        remaining = MAX_COMBINED_ATTACHMENT_TEXT_CHARS - total_chars
        if not text or remaining <= 0:
            continue
        text = text[:remaining]
        total_chars += len(text)
        result.append(
            {
                "filename": Path(str(payload.get("filename") or "tệp đính kèm")).name[:255],
                "content_type": str(payload.get("content_type") or "application/octet-stream")[:120],
                "kind": "image" if payload.get("kind") == "image" else "document",
                "size_bytes": max(0, int(payload.get("size_bytes") or 0)),
                "page_count": payload.get("page_count"),
                "truncated": bool(payload.get("truncated")),
                "text": text,
            }
        )
    return result


def compact_attachment_context(
    payloads: list[dict[str, Any]],
    *,
    max_chars: int = 6_000,
) -> str:
    blocks: list[str] = []
    remaining = max(0, max_chars)
    for payload in payloads:
        if remaining <= 0:
            break
        header = f"Tệp {payload.get('filename', 'đính kèm')}:\n"
        text = str(payload.get("text") or "").strip()
        block = (header + text)[:remaining]
        blocks.append(block)
        remaining -= len(block)
    return "\n\n".join(blocks)
