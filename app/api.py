from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
import time
import unicodedata
import uuid
from binascii import Error as BinasciiError
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from cryptography.exceptions import InvalidTag
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import and_, delete, func, select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user, optional_user, require_roles
from app.auth import router as auth_router
from app.core.config import Settings, get_settings
from app.core.observability import current_request_id, log_progress
from app.core.security import decrypt_text, encrypt_text
from app.db import get_db
from app.models import (
    Article,
    Artifact,
    ChatAnswerFeedback,
    ChatMessage,
    Conversation,
    ConversationSummary,
    LegalAnswerCache,
    LegalDocument,
    SignaturePacket,
    User,
    UserFeedback,
)
from app.schemas import (
    ArticleCreate,
    ArticleSearchRequest,
    ArticleUpdate,
    ArtifactCreate,
    ArtifactOut,
    ArtifactUpdate,
    ChatAnswerFeedbackOut,
    ChatAnswerFeedbackRequest,
    ChatAttachment,
    ChatAttachmentUploadOut,
    ChatRequest,
    ChatResponse,
    CompareContractRequest,
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdate,
    DraftContractRequest,
    FeedbackRequest,
    LegalDocumentDetailOut,
    LegalDocumentSectionOut,
    MessageOut,
    PrepareSignatureRequest,
    ReviewContractRequest,
    SourceOut,
    VerificationReport,
)
from app.services.ai import (
    ATTACHMENT_QA_SYSTEM_PROMPT,
    CONTRACT_SYSTEM_PROMPT,
    LEGAL_SYSTEM_PROMPT,
    GeminiError,
    GeminiService,
    untrusted_data_block,
    validate_citations,
)
from app.services.articles import ArticleResearchService
from app.services.chat_attachments import (
    MAX_CHAT_ATTACHMENT_BYTES,
    MAX_CHAT_ATTACHMENTS,
    MAX_COMBINED_ATTACHMENT_TEXT_CHARS,
    ChatAttachmentError,
    attachment_metadata,
    compact_attachment_context,
    create_attachment_token,
    decode_attachment_token,
    deserialize_attachment_context,
    extract_document_attachment,
    extracted_ocr_attachment,
    is_direct_attachment_question,
    select_relevant_attachment_context,
    serialize_attachment_context,
    validate_chat_attachment,
)
from app.services.chat_policy import chat_profile_for_route
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
from app.services.contract_docx import (
    build_contract_docx,
    contract_download_filename,
    normalize_contract_plain_text,
)
from app.services.conversation_memory import ConversationMemoryService
from app.services.embeddings import (
    VertexAIEmbeddingService,
    embedding_config_from_settings,
    get_embedding_service,
)
from app.services.evidence_gate import assess_source_relevance
from app.services.freshness import (
    LAW_CODE_RE,
    LegalFreshnessService,
)
from app.services.greetings import greeting_response
from app.services.legal_catalog import LegalCatalogService, parse_catalog_request
from app.services.query_rewrite import (
    rewrite_query_if_needed,
    should_rewrite_query,
)
from app.services.retrieval import (
    RetrievalService,
    build_answer_plan,
    build_context,
    classify_retrieval_route,
    compact_context_sources,
    format_source_locator,
    select_context_sources,
)
from app.services.semantic_cache import (
    CacheLookup,
    SemanticAnswerCacheService,
    legal_fingerprint,
)

router = APIRouter()
router.include_router(auth_router)
logger = logging.getLogger(__name__)
LEGAL_DATA_UNAVAILABLE_MESSAGE = "Dữ liệu không có sẵn"
AI_TEMPORARILY_UNAVAILABLE_MESSAGE = (
    "Dịch vụ AI tạm thời không khả dụng. Vui lòng thử lại sau."
)
_DIRECT_VALUE_QUESTION_RE = re.compile(
    r"\b(?:bao\s+nhiêu|bao\s+lâu|mấy|tỷ\s+lệ|phần\s+trăm|gấp\s+.+\s+lần|"
    r"mức\s+nào|thời\s+hạn)\b",
    re.IGNORECASE,
)
_MONEY_VALUE_RE = re.compile(
    r"\b\d[\d.,\s]*\s*(?:đồng|triệu|tỷ)(?:\s*/\s*(?:tháng|giờ|ngày))?\b",
    re.IGNORECASE,
)
_TIME_VALUE_RE = re.compile(
    r"\b(?:\d+[\d.,]*|một|hai|ba|bốn|năm|sáu|bảy|tám|chín|mười)\s+"
    r"(?:giờ|ngày|tháng|năm|tuần)\b",
    re.IGNORECASE,
)
_RATE_VALUE_RE = re.compile(
    r"(?:\b\d+(?:[.,]\d+)?\s*%|\b\d+(?:[.,]\d+)?\s*lần\b|"
    r"\b\d+(?:[.,]\d+)?\s*phần\s+trăm\b)",
    re.IGNORECASE,
)
_GENERIC_VALUE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:đồng|triệu|tỷ|%|lần|giờ|ngày|tháng|năm|tuần)\b",
    re.IGNORECASE,
)
_OUT_OF_SCOPE_ANSWER_RE = re.compile(
    r"(?:nằm\s+ngoài\s+phạm\s+vi|trợ\s+lý\s+chuyên\s+sâu\s+về\s+pháp\s+luật\s+lao\s+động|"
    r"cơ\s+sở\s+dữ\s+liệu\s+chuyên\s+ngành\s+lao\s+động)",
    re.IGNORECASE,
)


def _requires_direct_value(question: str) -> bool:
    return _DIRECT_VALUE_QUESTION_RE.search(str(question or "")) is not None


def _source_contains_requested_value(
    question: str,
    source: dict[str, Any],
) -> bool:
    """Require a value of the requested kind before a failed gate can fail open.

    Article numbers in citations are not evidence of an amount, duration or
    rate, so this deliberately inspects source text rather than citation data.
    """

    text = str(source.get("text") or "")
    normalized = _normalize_scope_text(question)
    if any(term in normalized for term in ("luong", "tien", "gia", "muc dong")):
        return _MONEY_VALUE_RE.search(text) is not None
    if any(
        term in normalized
        for term in ("bao lau", "thoi han", "bao truoc", "may ngay", "may thang")
    ):
        return _TIME_VALUE_RE.search(text) is not None
    if any(
        term in normalized
        for term in ("ty le", "phan tram", "gap", "may lan", "bao nhieu lan")
    ):
        return _RATE_VALUE_RE.search(text) is not None
    return _GENERIC_VALUE_RE.search(text) is not None

# ---------------------------------------------------------------------------
# Prompt-injection guard (Python layer — runs before LLM and catalog dispatch)
# Chặn các mẫu câu phổ biến cố ghi đè system prompt hoặc tiết lộ cấu hình
# ---------------------------------------------------------------------------
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    # English classic injection
    re.compile(r"\bignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?\b", re.IGNORECASE),
    re.compile(r"\b(?:forget|disregard)\s+(?:your\s+)?(?:instructions?|rules?|guidelines?)\b", re.IGNORECASE),
    re.compile(r"\b(?:reveal|show|print|output|display)\s+(?:your\s+)?(?:system\s+prompt|instructions?|config(?:uration)?)\b", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(?:a\s+)?(?:different|another|new|unrestricted)\b", re.IGNORECASE),
    # Vietnamese injection
    re.compile(r"\bbỏ\s+qua\s+(?:tất\s+cả\s+)?(?:quy\s+tắc|hướng\s+dẫn|chỉ\s+dẫn|lệnh)\b", re.IGNORECASE),
    re.compile(r"\btiết\s+lộ\s+(?:system\s+prompt|prompt\s+hệ\s+thống|cấu\s+hình|nội\s+dung\s+hệ\s+thống)\b", re.IGNORECASE),
]


def _check_prompt_injection(message: str) -> str | None:
    """Return a rejection string if the message matches a known injection pattern.

    This is a lightweight Python-layer guard that runs before the LLM is called.
    It complements (does not replace) the UNTRUSTED_DATA wrapper and system-prompt
    instruction in LEGAL_SYSTEM_PROMPT.
    Returns None if the message is clean.
    """
    for pat in _INJECTION_PATTERNS:
        if pat.search(message):
            logger.warning(
                "prompt_injection_blocked pattern=%s query_prefix=%s",
                pat.pattern[:60],
                message[:80],
            )
            return "Mình chỉ hỗ trợ các câu hỏi về pháp luật Việt Nam."
    return None


# ---------------------------------------------------------------------------
# Out-of-scope guard — các chủ đề rõ ràng nằm ngoài Pháp luật Lao động
# ---------------------------------------------------------------------------
_NON_LABOR_SCOPE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(?:luật|quy\s+định|xem\s+luật)?\s*đất\s+đai\b", re.IGNORECASE),
    re.compile(r"\b(?:thành\s+lập|đăng\s+ký|giấy\s+phép)\s+(?:công\s+ty|doanh\s+nghiệp)\b", re.IGNORECASE),
    re.compile(r"\b(?:luật|bộ\s+luật)\s+dân\s+sự\b", re.IGNORECASE),
    re.compile(
        r"\b(?:(?:tranh\s+chấp|khởi\s+kiện)\s+)?hợp\s+đồng\s+dân\s+sự\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:tranh\s+chấp|khởi\s+kiện)\s+dân\s+sự\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:tố\s+tụng\s+dân\s+sự|hình\s+sự|luật\s+hình\s+sự)\b", re.IGNORECASE),
    re.compile(r"\b(?:sổ\s+đỏ|sổ\s+hồng|quy\s+hoạch\s+đất|thu\s+hồi\s+đất|bất\s+động\s+sản)\b", re.IGNORECASE),
    re.compile(r"\b(?:hôn\s+nhân\s+gia\s+đình|ly\s+hôn|kết\s+hôn|thừa\s+kế|tài\s+sản\s+thừa\s+kế)\b", re.IGNORECASE),
    re.compile(r"\b(?:xử\s+lý\s+vi\s+phạm\s+hành\s+chính|vi\s+phạm\s+giao\s+thông|phạt\s+giao\s+thông|bằng\s+lái)\b", re.IGNORECASE),
]

_NON_LABOR_SCOPE_PHRASES = (
    "hop dong dan su",
    "tranh chap dan su",
    "khoi kien dan su",
    "to tung dan su",
    "bo luat dan su",
    "luat dan su",
)


def _normalize_scope_text(value: str) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        str(value or "").casefold().replace("đ", "d"),
    )
    without_marks = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    ).replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", without_marks))


def _check_non_labor_scope(message: str) -> str | None:
    """Detect queries clearly outside the Labor Law scope."""
    normalized_message = _normalize_scope_text(message)
    phrase_match = any(
        phrase in normalized_message
        for phrase in _NON_LABOR_SCOPE_PHRASES
    )
    for pat in _NON_LABOR_SCOPE_PATTERNS:
        if phrase_match or pat.search(message):
            logger.info("non_labor_scope_detected query=%s", message[:80])
            return (
                "VLegal AI hiện tại là trợ lý chuyên sâu về **Pháp luật Lao động Việt Nam "
                "và các chế độ liên quan đã có trong kho dữ liệu** (Bộ luật Lao động 2019, "
                "hợp đồng lao động, tiền lương, chế độ tiền lương khu vực công, thời giờ làm việc "
                "- nghỉ ngơi, bảo hiểm xã hội, an toàn lao động, việc làm, kỷ luật lao động, "
                "tranh chấp lao động...).\n\n"
                "Câu hỏi của bạn nằm ngoài phạm vi CSDL chuyên ngành Lao động hiện tại của hệ thống. "
                "Bạn có cần hỗ trợ câu hỏi nào liên quan đến Pháp luật Lao động không?"
            )
    return None


CONTRACT_TEMPLATES = [
    {"id": "employment", "name": "Hợp đồng lao động", "category": "Lao động"},
    {"id": "probation", "name": "Hợp đồng thử việc", "category": "Lao động"},
    {
        "id": "vocational_training",
        "name": "Hợp đồng đào tạo nghề",
        "category": "Lao động",
    },
    {
        "id": "employment_appendix",
        "name": "Phụ lục hợp đồng lao động",
        "category": "Lao động",
    },
    {
        "id": "employment_confidentiality",
        "name": "Thỏa thuận bảo mật trong quan hệ lao động",
        "category": "Lao động",
    },
]

_LABOR_CONTRACT_TEMPLATE_BY_ID = {item["id"]: item for item in CONTRACT_TEMPLATES}
_LABOR_CONTRACT_TEMPLATE_BY_NAME = {
    _normalize_scope_text(item["name"]): item for item in CONTRACT_TEMPLATES
}
_LABOR_CONTRACT_SIGNALS = (
    "hop dong lao dong",
    "nguoi lao dong",
    "nguoi su dung lao dong",
    "thu viec",
    "dao tao nghe",
    "vi tri cong viec",
    "noi lam viec",
    "tien luong",
    "bao hiem xa hoi",
    "thoi gio lam viec",
)


def _resolve_labor_contract_template(payload: DraftContractRequest) -> dict[str, str]:
    if payload.template_id:
        template = _LABOR_CONTRACT_TEMPLATE_BY_ID.get(payload.template_id.strip())
        if template:
            return template
        raise HTTPException(
            status_code=422,
            detail=(
                "Chỉ hỗ trợ soạn các loại hợp đồng và thỏa thuận "
                "liên quan trực tiếp đến lao động."
            ),
        )
    if payload.template_name:
        template = _LABOR_CONTRACT_TEMPLATE_BY_NAME.get(
            _normalize_scope_text(payload.template_name)
        )
        if template:
            return template
        raise HTTPException(
            status_code=422,
            detail=(
                "Chỉ hỗ trợ soạn các loại hợp đồng và thỏa thuận "
                "liên quan trực tiếp đến lao động."
            ),
        )
    return CONTRACT_TEMPLATES[0]


def _ensure_labor_contract_source(source_text: str) -> None:
    if not source_text or not looks_like_contract(source_text):
        return
    normalized = _normalize_scope_text(source_text[:20_000])
    if not any(signal in normalized for signal in _LABOR_CONTRACT_SIGNALS):
        raise HTTPException(
            status_code=422,
            detail=(
                "Tài liệu tải lên không có dấu hiệu là hợp đồng "
                "liên quan đến lao động."
            ),
        )


@router.post("/contracts/extract")
async def extract_contract_file(
    document: UploadFile = File(...),
    _: User = Depends(current_user),
) -> dict[str, Any]:
    data = await document.read(MAX_DOCUMENT_BYTES + 1)
    try:
        extracted = await run_in_threadpool(
            extract_contract_document,
            data,
            document.filename or "hop-dong",
            document.content_type,
        )
    except ContractDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        await document.close()
    return {
        "filename": extracted.filename,
        "text": extracted.text,
        "original_chars": extracted.original_chars,
        "truncated": extracted.truncated,
        "page_count": extracted.page_count,
    }


REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "summary",
        "contract_type",
        "party_perspective",
        "key_terms",
        "clause_reviews",
        "missing_clauses",
        "risks",
        "recommendations",
    ],
    "properties": {
        "summary": {
            "type": "string",
            "description": "Tóm tắt có [S1], [S2] ngay sau từng nhận định pháp lý.",
        },
        "contract_type": {"type": "string"},
        "party_perspective": {"type": "string"},
        "key_terms": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "value", "assessment"],
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "assessment": {"type": "string"},
                },
            },
        },
        "clause_reviews": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "clause",
                    "assessment",
                    "issue",
                    "suggested_revision",
                    "citations",
                ],
                "properties": {
                    "clause": {"type": "string"},
                    "assessment": {
                        "type": "string",
                        "enum": ["favorable", "neutral", "unfavorable", "missing"],
                    },
                    "issue": {"type": "string"},
                    "suggested_revision": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": r"^(?:S\d+|\[S\d+\])$",
                        },
                    },
                },
            },
        },
        "missing_clauses": {
            "type": "array",
            "items": {"type": "string"},
        },
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["level", "title", "detail", "recommendation", "citations"],
                "properties": {
                    "level": {"type": "string", "enum": ["low", "medium", "high"]},
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "recommendation": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": r"^(?:S\d+|\[S\d+\])$",
                        },
                    },
                },
            },
        },
        "recommendations": {
            "type": "array",
            "items": {
                "type": "string",
                "description": "Gắn [S1], [S2] sau mọi khuyến nghị dựa trên pháp luật.",
            },
        },
    },
}


COMPARE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "summary",
        "important_changes",
        "differences",
        "risks",
        "recommendation",
    ],
    "properties": {
        "summary": {
            "type": "string",
            "description": "Tóm tắt có [S1], [S2] ngay sau từng nhận định pháp lý.",
        },
        "differences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "type",
                    "category",
                    "severity",
                    "clause",
                    "before",
                    "after",
                    "legal_impact",
                    "citations",
                ],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["added", "deleted", "modified"],
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "money",
                            "term",
                            "responsibility",
                            "penalty",
                            "termination",
                            "other",
                        ],
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "clause": {"type": "string"},
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                    "legal_impact": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "pattern": r"^(?:S\d+|\[S\d+\])$",
                        },
                    },
                },
            },
        },
        "important_changes": {
            "type": "array",
            "items": {"type": "string"},
        },
        "risks": {"type": "array", "items": REVIEW_SCHEMA["properties"]["risks"]["items"]},
        "recommendation": {
            "type": "string",
            "description": "Gắn [S1], [S2] sau mọi khuyến nghị dựa trên pháp luật.",
        },
    },
}


def retrieval_service(request: Request) -> RetrievalService:
    return request.app.state.retrieval


def freshness_service(request: Request) -> LegalFreshnessService:
    return request.app.state.freshness


def ai_service(request: Request) -> GeminiService:
    return request.app.state.ai


def embedding_service(
    settings: Settings = Depends(get_settings),
) -> VertexAIEmbeddingService:
    return get_embedding_service(embedding_config_from_settings(settings))


def article_research_service(request: Request) -> ArticleResearchService:
    return request.app.state.article_research


def conversation_memory_service(request: Request) -> ConversationMemoryService:
    return request.app.state.conversation_memory


def semantic_answer_cache_service(request: Request) -> SemanticAnswerCacheService:
    return request.app.state.semantic_answer_cache


@router.post(
    "/chat/attachments",
    response_model=ChatAttachmentUploadOut,
)
async def upload_chat_attachment(
    attachment: UploadFile = File(...),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    ai: GeminiService = Depends(ai_service),
) -> ChatAttachmentUploadOut:
    data = await attachment.read(MAX_CHAT_ATTACHMENT_BYTES + 1)
    try:
        validated = validate_chat_attachment(
            data,
            attachment.filename or "tep-dinh-kem",
            attachment.content_type,
        )
        if validated.requires_ocr:
            ocr_text = await ai.extract_attachment_text(
                validated.data,
                validated.content_type,
                validated.filename,
            )
            extracted = extracted_ocr_attachment(validated, ocr_text)
        else:
            try:
                extracted = await run_in_threadpool(
                    extract_document_attachment,
                    validated,
                )
            except ChatAttachmentError as exc:
                is_scanned_pdf = (
                    validated.content_type == "application/pdf"
                    and "Không đọc được nội dung văn bản" in str(exc)
                )
                if not is_scanned_pdf:
                    raise
                ocr_text = await ai.extract_attachment_text(
                    validated.data,
                    validated.content_type,
                    validated.filename,
                )
                extracted = extracted_ocr_attachment(validated, ocr_text)
    except ChatAttachmentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GeminiError as exc:
        logger.warning(
            "Attachment OCR unavailable error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Không thể đọc ảnh hoặc tài liệu scan lúc này. Vui lòng thử lại sau.",
        ) from exc
    finally:
        await attachment.close()

    metadata = extracted.metadata()
    return ChatAttachmentUploadOut(
        **metadata,
        token=create_attachment_token(
            extracted,
            str(user.id),
            settings,
        ),
        preview=extracted.text[:320],
    )


def _hash_content(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _artifact_out(artifact: Artifact, settings: Settings) -> ArtifactOut:
    content = decrypt_text(artifact.content_ciphertext, settings)
    if artifact.kind == "CONTRACT_DRAFT":
        content = normalize_contract_plain_text(content, artifact.title)
    return ArtifactOut(
        id=artifact.id,
        kind=artifact.kind,
        title=artifact.title,
        content=content,
        metadata=artifact.metadata_json,
        status=artifact.status,
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
    )


def _message_verification_out(value: Any) -> VerificationReport | None:
    if not isinstance(value, dict) or not value:
        return None

    payload = dict(value)
    if not isinstance(payload.get("items"), list):
        payload["items"] = []
    try:
        return VerificationReport.model_validate(payload)
    except ValidationError:
        logger.warning("Ignoring malformed verification payload in stored chat message")
        return VerificationReport(
            checked=bool(payload.get("checked", False)),
            all_current=bool(payload.get("all_current", False)),
            note=payload.get("note") if isinstance(payload.get("note"), str) else "",
        )


def _message_sources_out(value: Any) -> list[SourceOut]:
    if not isinstance(value, list):
        return []

    sources: list[SourceOut] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            sources.append(SourceOut.model_validate(item))
        except ValidationError:
            logger.warning("Ignoring malformed source payload in stored chat message")
    return sources


def _message_attachments_out(value: Any) -> list[ChatAttachment]:
    if not isinstance(value, list):
        return []
    attachments: list[ChatAttachment] = []
    for item in value[:MAX_CHAT_ATTACHMENTS]:
        if not isinstance(item, dict):
            continue
        try:
            attachments.append(ChatAttachment.model_validate(item))
        except ValidationError:
            logger.warning("Ignoring malformed attachment metadata in stored chat message")
    return attachments


def _stored_attachment_payloads(
    message: ChatMessage,
    settings: Settings,
) -> list[dict[str, Any]]:
    ciphertext = getattr(message, "attachment_context_ciphertext", None)
    if not ciphertext:
        return []
    try:
        return deserialize_attachment_context(decrypt_text(ciphertext, settings))
    except (BinasciiError, InvalidTag, UnicodeDecodeError, ValueError):
        logger.warning(
            "Ignoring unreadable chat attachment context message_id=%s",
            message.id,
        )
        return []


def _request_attachment_payloads(
    tokens: list[Any],
    user_id: uuid.UUID,
    settings: Settings,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    remaining = MAX_COMBINED_ATTACHMENT_TEXT_CHARS
    for item in tokens[:MAX_CHAT_ATTACHMENTS]:
        token = str(getattr(item, "token", "") or "")
        if not token or token in seen_tokens:
            continue
        seen_tokens.add(token)
        try:
            decoded = decode_attachment_token(token, str(user_id), settings)
        except ChatAttachmentError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        payload = {
            **attachment_metadata(decoded),
            "text": str(decoded.get("text") or ""),
        }
        if remaining <= 0:
            break
        text = str(payload.get("text") or "")
        if len(text) > remaining:
            payload["text"] = text[:remaining]
            payload["truncated"] = True
        remaining -= len(str(payload.get("text") or ""))
        payloads.append(payload)
    return payloads


def _retrieval_query_with_attachments(
    query: str,
    payloads: list[dict[str, Any]],
) -> str:
    if not payloads:
        return query
    attachment_hint = compact_attachment_context(payloads, max_chars=3_000)
    return f"{query}\n\nNội dung tệp đính kèm liên quan:\n{attachment_hint}"[:8_000]


def _attachment_citation_sources(
    payloads: list[dict[str, Any]],
    *,
    start_index: int,
) -> list[dict[str, Any]]:
    return [
        {
            "source_id": f"S{start_index + index}",
            "score": 1.0,
            "chunk_type": "user_attachment",
            "citation": f"Tệp người dùng cung cấp: {payload['filename']}",
            "title": payload["filename"],
            "text": str(payload.get("text") or "").strip(),
            "reasons": ["user_attachment"],
            "doc_id": None,
            "source_url": None,
        }
        for index, payload in enumerate(payloads)
    ]


def _message_content_out(message: ChatMessage, settings: Settings) -> str:
    try:
        return decrypt_text(message.content_ciphertext, settings)
    except (BinasciiError, InvalidTag, UnicodeDecodeError, ValueError):
        logger.exception("Cannot decrypt stored chat message message_id=%s", message.id)
        return "Không thể khôi phục nội dung tin nhắn này."


def _message_out(
    message: ChatMessage,
    settings: Settings,
    feedback_rating: str | None = None,
) -> MessageOut:
    role = str(message.role).lower()
    if role not in {"user", "assistant"}:
        logger.warning("Normalizing unsupported stored chat role role=%s message_id=%s", role, message.id)
        role = "assistant"
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        role=role,
        content=_message_content_out(message, settings),
        sources=_message_sources_out(message.sources),
        verification=_message_verification_out(message.verification),
        attachments=_message_attachments_out(
            getattr(message, "attachments", []),
        ),
        feedback_rating=(
            feedback_rating.lower()
            if feedback_rating in {"GOOD", "BAD"}
            else None
        ),
        created_at=message.created_at,
    )


async def _enrich_stored_source_urls(
    db: AsyncSession,
    messages: list[MessageOut],
) -> None:
    """Attach official links to sources saved before URL enrichment."""

    missing_by_code: dict[str, list[SourceOut]] = {}
    for message in messages:
        for source in message.sources:
            if source.source_url:
                continue
            label = f"{source.citation} {source.title}".upper()
            match = LAW_CODE_RE.search(label)
            if match:
                missing_by_code.setdefault(
                    match.group(0).upper(),
                    [],
                ).append(source)
    if not missing_by_code:
        return

    documents = (
        await db.scalars(
            select(LegalDocument)
            .where(
                func.upper(LegalDocument.code).in_(
                    list(missing_by_code)
                ),
                LegalDocument.source_url.is_not(None),
            )
            .order_by(
                LegalDocument.version.desc(),
                LegalDocument.verified_at.desc().nullslast(),
            )
        )
    ).all()
    official_urls: dict[str, str] = {}
    for document in documents:
        source_url = str(document.source_url or "").strip()
        if source_url:
            official_urls.setdefault(
                document.code.strip().upper(),
                source_url,
            )
    for code, sources in missing_by_code.items():
        source_url = official_urls.get(code)
        if not source_url:
            continue
        for source in sources:
            source.source_url = source_url


def _conversation_out(conversation: Conversation, count: int = 0) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        title=conversation.title,
        status=conversation.status,
        retrieval_mode=conversation.retrieval_mode,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        message_count=count,
    )


async def _owned_conversation(db: AsyncSession, conversation_id: uuid.UUID, user: User) -> Conversation:
    conversation = await db.scalar(
        select(Conversation).where(Conversation.id == conversation_id, Conversation.user_id == user.id)
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện")
    return conversation


async def _owned_feedback_target(
    db: AsyncSession,
    message_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[ChatMessage, ChatMessage]:
    message = await db.scalar(
        select(ChatMessage)
        .join(
            Conversation,
            Conversation.id == ChatMessage.conversation_id,
        )
        .where(
            ChatMessage.id == message_id,
            Conversation.user_id == user_id,
            ChatMessage.role == "ASSISTANT",
            ChatMessage.status == "COMPLETED",
        )
    )
    if message is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy câu trả lời để đánh giá",
        )
    question = await db.scalar(
        select(ChatMessage)
        .where(
            ChatMessage.conversation_id == message.conversation_id,
            ChatMessage.role == "USER",
            ChatMessage.status == "COMPLETED",
            ChatMessage.message_sequence < message.message_sequence,
        )
        .order_by(ChatMessage.message_sequence.desc())
        .limit(1)
    )
    if question is None:
        raise HTTPException(
            status_code=409,
            detail="Không tìm thấy câu hỏi gốc của câu trả lời",
        )
    return message, question


_FEEDBACK_STOP_WORDS = {
    "cua",
    "cho",
    "cac",
    "voi",
    "trong",
    "theo",
    "duoc",
    "khong",
    "nhung",
    "mot",
    "nay",
    "do",
    "la",
    "va",
    "thi",
    "toi",
    "ban",
}


def _feedback_terms(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", value.lower())
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return {
        term
        for term in re.findall(r"[a-z0-9]{2,}", normalized)
        if term not in _FEEDBACK_STOP_WORDS
    }


def _feedback_question_similarity(left: str, right: str) -> float:
    left_terms = _feedback_terms(left)
    right_terms = _feedback_terms(right)
    if not left_terms or not right_terms:
        return 0.0
    overlap = len(left_terms.intersection(right_terms))
    return overlap / max(1, min(len(left_terms), len(right_terms)))


async def _load_approved_answer_examples(
    db: AsyncSession,
    user_id: uuid.UUID,
    question: str,
    settings: Settings,
    *,
    limit: int = 2,
) -> list[dict[str, str]]:
    scalars = getattr(db, "scalars", None)
    if not callable(scalars):
        return []
    try:
        rows = (
            await scalars(
                select(ChatAnswerFeedback)
                .where(
                    ChatAnswerFeedback.user_id == user_id,
                    ChatAnswerFeedback.rating == "GOOD",
                )
                .order_by(ChatAnswerFeedback.updated_at.desc())
                .limit(60)
            )
        ).all()
    except Exception:
        logger.exception("Cannot load approved HITL answer examples")
        return []

    ranked: list[tuple[float, dict[str, str]]] = []
    for row in rows:
        if not isinstance(row, ChatAnswerFeedback):
            continue
        try:
            approved_question = decrypt_text(
                row.question_ciphertext,
                settings,
            )
            approved_answer = decrypt_text(
                row.answer_ciphertext,
                settings,
            )
        except (BinasciiError, InvalidTag, UnicodeDecodeError, ValueError):
            logger.warning(
                "Ignoring unreadable approved feedback feedback_id=%s",
                row.id,
            )
            continue
        similarity = _feedback_question_similarity(
            question,
            approved_question,
        )
        if similarity < 0.4:
            continue
        ranked.append(
            (
                similarity,
                {
                    "question": approved_question[:1500],
                    "approved_answer": approved_answer[:3500],
                },
            )
        )
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [example for _, example in ranked[:limit]]


async def _legal_sources(
    query: str,
    retrieval: RetrievalService,
    _freshness: LegalFreshnessService,
    *,
    allow_empty: bool = False,
    telemetry: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    operation_started = time.perf_counter()

    def add_timing(name: str, started_at: float) -> None:
        if telemetry is None:
            return
        elapsed = round((time.perf_counter() - started_at) * 1000, 1)
        telemetry[name] = round(float(telemetry.get(name, 0.0)) + elapsed, 1)
    log_progress(
        logger,
        "legal_sources",
        "started",
        operation_started,
        allow_empty=allow_empty,
    )

    async def retrieve_sources(retrieval_query: str) -> list[dict[str, Any]]:
        return await retrieval.retrieve(retrieval_query)

    def unavailable_result() -> tuple[list[dict[str, Any]], dict[str, Any]]:
        log_progress(
            logger,
            "legal_sources",
            "completed",
            operation_started,
            outcome="data_unavailable",
            source_count=0,
        )
        return (
            [],
            VerificationReport(
                checked=False,
                all_current=False,
                checked_at=datetime.now(UTC),
                items=[],
                note=LEGAL_DATA_UNAVAILABLE_MESSAGE,
            ).model_dump(mode="json"),
        )

    def freshness_fast_path_result(
        rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        retained_sources = [dict(source) for source in rows]
        for index, source in enumerate(retained_sources, start=1):
            source["source_id"] = f"S{index}"
        log_progress(
            logger,
            "legal_sources",
            "completed",
            operation_started,
            outcome="scheduled_freshness_index",
            source_count=len(retained_sources),
        )
        return (
            retained_sources,
            VerificationReport(
                checked=True,
                all_current=True,
                checked_at=datetime.now(UTC),
                items=[],
                note="Hiệu lực văn bản được đối chiếu định kỳ từ chỉ mục pháp luật.",
            ).model_dump(mode="json"),
        )

    source_limit = 16

    def usable_sources(rows: Any) -> list[dict[str, Any]]:
        filtered = [
            source
            for source in rows
            if isinstance(source, dict)
            and str(source.get("text") or "").strip()
            and str(source.get("citation") or source.get("title") or "").strip()
        ]
        # The freshness limit applies to unique instruments, not chunks.  A
        # multi-abstract answer often needs many articles of the same code, so
        # cutting at 16 chunks discarded valid evidence unnecessarily.
        selected: list[dict[str, Any]] = []
        admitted_laws: set[str] = set()
        for source in select_context_sources(filtered):
            law_code = source_law_code(source)
            if law_code not in admitted_laws and len(admitted_laws) >= source_limit:
                continue
            admitted_laws.add(law_code)
            selected.append(source)
        return selected

    def source_law_code(source: dict[str, Any]) -> str:
        label = f"{source.get('citation', '')} {source.get('title', '')}"
        match = LAW_CODE_RE.search(label.upper())
        if match:
            return match.group(0).upper()
        return str(
            source.get("doc_id") or source.get("title") or "Không rõ"
        )[:120].strip().upper()

    retrieval_started = time.perf_counter()
    log_progress(logger, "legal_sources", "retrieval_started", operation_started)
    try:
        sources = usable_sources(await retrieve_sources(query))
    except Exception as exc:
        logger.warning("Retrieval failed: %s", exc)
        sources = []
    add_timing("retrieval", retrieval_started)
    log_progress(
        logger,
        "legal_sources",
        "retrieval_completed",
        operation_started,
        phase_ms=round((time.perf_counter() - retrieval_started) * 1000),
        source_count=len(sources),
    )
    if not sources:
        if allow_empty:
            return unavailable_result()
        raise HTTPException(
            status_code=422,
            detail=(
                "Kho dữ liệu hiện không có căn cứ pháp lý đủ liên quan để trả lời "
                "an toàn. Hệ thống sẽ không suy đoán hoặc viện dẫn văn bản ngoài dữ liệu."
            ),
        )

    # Legal status is refreshed by the scheduled corpus job. Request handling
    # only reads the verified index, so external search latency cannot block
    # or fail a chat response.
    return freshness_fast_path_result(sources)


async def _evidence_gated_sources(
    *,
    original_question: str,
    retrieval_query: str,
    sources: list[dict[str, Any]],
    verification: dict[str, Any],
    ai: GeminiService,
    retrieval: RetrievalService,
    freshness: LegalFreshnessService,
    settings: Settings,
    telemetry: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    if not settings.evidence_gate_enabled or not sources:
        return sources, verification, retrieval_query

    started = time.perf_counter()

    partial_evidence_note = (
        "Nguồn hiện có chỉ hỗ trợ một phần câu hỏi. Hãy nêu rõ phần "
        "chưa đủ căn cứ, sau đó vẫn giải thích những thông tin liên quan "
        "được nguồn chứng minh; không trả lời 'Dữ liệu không có sẵn'."
    )

    def partial_verification(report: dict[str, Any]) -> dict[str, Any]:
        updated = dict(report)
        existing_note = str(updated.get("note") or "").strip()
        updated["note"] = " ".join(
            part for part in (existing_note, partial_evidence_note) if part
        )
        return updated

    def selected_sources(
        rows: list[dict[str, Any]],
        selected_ids: tuple[str, ...],
    ) -> list[dict[str, Any]]:
        allowed = set(selected_ids)
        selected = [dict(row) for row in rows if row.get("source_id") in allowed]
        for index, row in enumerate(selected, start=1):
            row["source_id"] = f"S{index}"
        return selected

    def deterministic_fallback_sources(
        rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Keep only rows already proven by deterministic retrieval signals.

        Semantic intent fallbacks exist so the LLM gate can inspect synonyms;
        they must never be promoted to answer evidence when that gate fails.
        """

        asks_for_direct_value = _requires_direct_value(original_question)
        safe_ids = tuple(
            str(row.get("source_id") or "")
            for row in rows
            if (
                "intent_anchor_semantic_fallback"
                not in {str(reason) for reason in row.get("reasons", [])}
                and (
                    not asks_for_direct_value
                    or _source_contains_requested_value(original_question, row)
                )
            )
        )
        return selected_sources(rows, safe_ids)

    first = await assess_source_relevance(
        ai,
        original_question=original_question,
        retrieval_query=retrieval_query,
        sources=sources,
        timeout_seconds=settings.evidence_gate_timeout_seconds,
        max_sources=settings.evidence_gate_max_sources,
    )
    first_selected = selected_sources(sources, first.relevant_source_ids)
    first_related = selected_sources(sources, first.related_source_ids)
    semantic_fallback = any(
        "intent_anchor_semantic_fallback" in source.get("reasons", [])
        for source in sources
    )
    log_progress(
        logger,
        "evidence_gate",
        "first_pass_completed",
        started,
        coverage=first.coverage,
        failed=first.failed,
        refined=bool(first.refined_search_query),
        related_count=len(first_related),
        selected_count=len(first_selected),
    )
    if first.failed:
        if telemetry is not None:
            telemetry["evidence_gate"] = round(
                (time.perf_counter() - started) * 1000,
                1,
            )
        safe_fallback = deterministic_fallback_sources(sources)
        return (
            safe_fallback,
            (
                partial_verification(verification)
                if semantic_fallback or safe_fallback
                else verification
            ),
            retrieval_query,
        )
    if first.coverage == "sufficient" and first_selected:
        if telemetry is not None:
            telemetry["evidence_gate"] = round(
                (time.perf_counter() - started) * 1000,
                1,
            )
        return first_selected, verification, retrieval_query

    refined_query = first.refined_search_query
    if refined_query:
        refined_sources, refined_verification = await _legal_sources(
            refined_query,
            retrieval,
            freshness,
            allow_empty=True,
            telemetry=telemetry,
        )
        if refined_sources:
            second = await assess_source_relevance(
                ai,
                original_question=original_question,
                retrieval_query=refined_query,
                sources=refined_sources,
                timeout_seconds=settings.evidence_gate_timeout_seconds,
                max_sources=settings.evidence_gate_max_sources,
            )
            second_selected = selected_sources(
                refined_sources,
                second.relevant_source_ids,
            )
            second_related = selected_sources(
                refined_sources,
                second.related_source_ids,
            )
            log_progress(
                logger,
                "evidence_gate",
                "refined_pass_completed",
                started,
                coverage=second.coverage,
                failed=second.failed,
                related_count=len(second_related),
                selected_count=len(second_selected),
            )
            if second_selected:
                if telemetry is not None:
                    telemetry["evidence_gate"] = round(
                        (time.perf_counter() - started) * 1000,
                        1,
                    )
                return (
                    second_selected,
                    (
                        partial_verification(refined_verification)
                        if second.failed or second.coverage != "sufficient"
                        else refined_verification
                    ),
                    refined_query,
                )
            if second_related:
                if telemetry is not None:
                    telemetry["evidence_gate"] = round(
                        (time.perf_counter() - started) * 1000,
                        1,
                    )
                return (
                    second_related,
                    partial_verification(refined_verification),
                    refined_query,
                )

    if telemetry is not None:
        telemetry["evidence_gate"] = round(
            (time.perf_counter() - started) * 1000,
            1,
        )
    if first_selected:
        return first_selected, partial_verification(verification), retrieval_query
    if first_related:
        return first_related, partial_verification(verification), retrieval_query

    # Retrieval has already rejected rows without query evidence. The LLM gate
    # may still be overly conservative for a colloquial definition or for a
    # question whose exact requested value is missing. Preserve a small,
    # grounded context so generation can explain what is supported and state
    # the missing part explicitly instead of collapsing to an empty answer.
    fallback_sources = deterministic_fallback_sources(
        sources[: settings.evidence_gate_max_sources]
    )
    log_progress(
        logger,
        "evidence_gate",
        "partial_sources_retained",
        started,
        reason="gate_selected_none",
        source_count=len(fallback_sources),
    )
    return (
        fallback_sources,
        partial_verification(verification),
        retrieval_query,
    )

def _verification_prompt(verification: dict[str, Any]) -> str:
    return untrusted_data_block("VERIFICATION_REPORT", verification)


def _summary_prompt(summary: str) -> str:
    if not summary:
        return "(Chưa có tóm tắt)"
    return untrusted_data_block("CONVERSATION_SUMMARY", summary)


def _chat_history_prompt(turns: list[tuple[str, str]]) -> str:
    if not turns:
        return "(Không có hội thoại trước đó)"
    labels = {"USER": "Người dùng", "ASSISTANT": "Trợ lý", "user": "Người dùng", "assistant": "Trợ lý"}
    history = [
        {
            "role": labels.get(role, role),
            "content": content[:2000],
        }
        for role, content in turns[-8:]
    ]
    return untrusted_data_block("CONVERSATION_HISTORY", history)


def _validate_narrative_claims(
    values: str | list[str],
    allowed_ids: list[str],
) -> None:
    items = [values] if isinstance(values, str) else values
    for value in items:
        validate_citations(
            value,
            allowed_ids,
            require=False,
            require_claim_coverage=True,
        )


_LEGAL_INSTRUMENT_MENTION_RE = re.compile(
    r"(?<!pháp )\b(?:Bộ luật|Luật|Nghị định|Thông tư|Nghị quyết|"
    r"Văn bản hợp nhất)\s+",
    re.IGNORECASE,
)
_GENERIC_INSTRUMENT_CONTINUATIONS = (
    "nay",
    "do",
    "tren",
    "hien hanh",
    "co lien quan",
    "viet nam",
    "quy dinh",
)


def _normalized_legal_reference(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or ""))
    without_marks = "".join(
        "d" if character in {"Đ", "đ"} else character
        for character in normalized
        if unicodedata.category(character) != "Mn"
    )
    # Instrument titles are often written with optional punctuation, for
    # example "Luật An toàn, vệ sinh lao động" versus "Luật An toàn vệ sinh
    # lao động". Punctuation is not evidence that these are different laws.
    return re.sub(
        r"\s+",
        " ",
        re.sub(r"[^0-9A-Za-z]+", " ", without_marks),
    ).strip().lower()


def _validate_grounded_legal_references(
    value: str,
    sources: list[dict[str, Any]],
) -> None:
    """Reject instrument codes and titles that do not exist in model context."""

    allowed_codes = {
        match.group(0).upper()
        for source in sources
        for match in LAW_CODE_RE.finditer(
            f"{source.get('citation', '')} {source.get('title', '')}"
        )
    }
    referenced_codes = {
        match.group(0).upper() for match in LAW_CODE_RE.finditer(value)
    }
    unknown_codes = referenced_codes - allowed_codes
    if unknown_codes:
        logger.warning(
            "legal_reference validation rejected unknown_codes=%s allowed_codes=%s",
            unknown_codes,
            allowed_codes,
        )
        raise GeminiError(
            "Câu trả lời nhắc đến số hiệu văn bản không có trong nguồn: "
            + ", ".join(sorted(unknown_codes))
        )

    allowed_titles: set[str] = {
        "bo luat lao dong",
        "bo luat lao dong 2019",
        "luat lao dong",
    }
    for source in sources:
        raw_title = str(
            source.get("citation") or source.get("title") or ""
        ).split(">", 1)[0]
        raw_title = re.sub(r"\s*\([^)]*\)\s*$", "", raw_title).strip()
        title = _normalized_legal_reference(raw_title)
        if title:
            allowed_titles.add(title)
            if title.startswith("bo luat "):
                allowed_titles.add(title.removeprefix("bo "))

    normalized_answer = _normalized_legal_reference(value)
    for match in _LEGAL_INSTRUMENT_MENTION_RE.finditer(value):
        start = match.start()
        normalized_tail = _normalized_legal_reference(value[start : start + 140])
        after_marker = _normalized_legal_reference(value[match.end() : match.end() + 80])
        if after_marker.startswith(_GENERIC_INSTRUMENT_CONTINUATIONS):
            continue
        if any(
            normalized_tail.startswith(title)
            for title in allowed_titles
        ):
            continue
        if any(
            _normalized_legal_reference(code) in normalized_tail
            for code in allowed_codes
        ):
            continue
        # A source title may occur immediately before a parenthetical or an
        # inline citation and therefore not be captured by startswith above.
        if any(
            title in normalized_answer[
                max(0, start - 10) : start + max(160, len(title) + 20)
            ]
            for title in allowed_titles
        ):
            continue
        excerpt = " ".join(value[start : start + 80].split())
        logger.warning(
            "legal_reference validation rejected excerpt=%s allowed_titles=%s allowed_codes=%s",
            excerpt,
            allowed_titles,
            allowed_codes,
        )
        raise GeminiError(
            f"Câu trả lời nhắc đến văn bản không có trong nguồn: {excerpt}"
        )


def _validate_professional_legal_opening(value: str) -> None:
    """Require a direct, cited legal opening instead of a generic preamble."""

    stripped = str(value or "").lstrip()
    if not stripped.startswith("Theo "):
        raise GeminiError('Câu trả lời pháp lý phải mở đầu trực tiếp bằng "Theo".')
    opening_paragraph = re.split(r"\n\s*\n", stripped, maxsplit=1)[0]
    if not re.search(r"\[S\d+\]", opening_paragraph, re.IGNORECASE):
        raise GeminiError(
            "Đoạn mở đầu phải chứa căn cứ nguồn cho kết luận trực tiếp."
        )


_ANSWER_CONCEPT_GENERIC_TERMS = {
    "cach",
    "che",
    "do",
    "dung",
    "huong",
    "lao",
    "luong",
    "muc",
    "nghia",
    "nguoi",
    "phap",
    "quyen",
    "tien",
    "tinh",
    "thu",
    "tuc",
    "viec",
}


class _AnswerCoverageError(GeminiError):
    """A grounded answer omitted a requested concept after synthesis."""


def _answer_validation_kind(exc: BaseException) -> str:
    if isinstance(exc, _AnswerCoverageError):
        return "answer_plan_coverage"
    message = _normalized_legal_reference(str(exc))
    if "trich dan" in message or "citation" in message:
        return "citation"
    if "so hieu van ban" in message or "van ban khong co trong nguon" in message:
        return "legal_reference"
    if "mo dau" in message or "bat dau" in message:
        return "opening"
    return "grounding"


def _normalize_citations_deterministically(value: str, allowed_ids: list[str]) -> str:
    """Fix common syntax & formatting issues in citations deterministically without LLM calls.
    
    Handles:
    - Grouped citations: [S1, S2] or [S1; S2] -> [S1] [S2]
    - Case normalization: [s1] -> [S1]
    - Parenthesized citations: (S1) or (S1, S2) -> [S1] [S2]
    - Period position: . [S1] -> [S1].
    - Spacing around bracketed citations
    """
    if not value or not allowed_ids:
        return value

    allowed_set = {id.upper() for id in allowed_ids}

    # 1. Split grouped citations inside brackets: [S1, S2] -> [S1] [S2]
    def _fix_grouped_brackets(match: re.Match[str]) -> str:
        inner = match.group(1)
        tokens = re.split(r"[,;]\s*", inner)
        items = []
        for token in tokens:
            cleaned = token.strip().upper()
            if cleaned in allowed_set:
                items.append(f"[{cleaned}]")
            else:
                items.append(token.strip())
        return " ".join(items)

    normalized = re.sub(r"\[([S|s]\d+(?:\s*[,;]\s*[S|s]\d+)+)\]", _fix_grouped_brackets, value)

    # 2. Case normalization for lower case [s1] -> [S1]
    for sid in allowed_ids:
        sid_upper = sid.upper()
        sid_lower = sid.lower()
        if sid_lower != sid_upper:
            normalized = re.sub(rf"\[{re.escape(sid_lower)}\]", f"[{sid_upper}]", normalized)

    # 3. Parentheses to brackets: (S1) -> [S1]
    def _fix_grouped_parens(match: re.Match[str]) -> str:
        inner = match.group(1)
        tokens = re.split(r"[,;]\s*", inner)
        items = []
        all_valid = True
        for token in tokens:
            cleaned = token.strip().upper()
            if cleaned in allowed_set:
                items.append(f"[{cleaned}]")
            else:
                all_valid = False
                break
        if all_valid and items:
            return " ".join(items)
        return match.group(0)

    normalized = re.sub(r"\(([S|s]\d+(?:\s*[,;]\s*[S|s]\d+)*)\)", _fix_grouped_parens, normalized)

    # 4. Fix period before citation: . [S1] -> [S1].
    normalized = re.sub(r"\.\s*(\[(?:S\d+)(?:\s*\[S\d+\])*\])", r" \1.", normalized)

    # 5. Fix missing space before citation: word[S1] -> word [S1]
    normalized = re.sub(r"([^\s\[({])(\[S\d+\])", r"\1 \2", normalized)

    return normalized


def _validate_answer_safety(
    value: str,
    *,
    allowed_ids: list[str],
    sources: list[dict[str, Any]] | None,
) -> None:
    """Validate citations and reject legal instruments absent from context."""

    validate_citations(
        value,
        allowed_ids,
        require_claim_coverage=True,
    )
    if sources is not None:
        _validate_grounded_legal_references(value, sources)


def _validate_answer_plan_coverage(
    value: str,
    answer_plan: dict[str, Any] | None,
) -> None:
    """Reject a cited answer that discusses adjacent law but misses the issue."""

    if not answer_plan:
        return
    if _OUT_OF_SCOPE_ANSWER_RE.search(value):
        raise _AnswerCoverageError(
            "Câu trả lời từ chối theo phạm vi mặc dù hệ thống đã cung cấp căn cứ liên quan."
        )
    raw_anchors = answer_plan.get("intent_anchor_phrases")
    if isinstance(raw_anchors, list):
        normalized_answer = _normalized_legal_reference(value)
        anchors = [
            _normalized_legal_reference(str(anchor))
            for anchor in raw_anchors
            if str(anchor).strip()
        ]
        if anchors and not any(
            anchor in normalized_answer
            for anchor in anchors
        ):
            raise _AnswerCoverageError(
                "Câu trả lời chưa giải quyết đúng khái niệm hoặc đại lượng được hỏi."
            )
    raw_concepts = answer_plan.get("required_concepts")
    if not isinstance(raw_concepts, list):
        return

    normalized_answer = _normalized_legal_reference(value)
    missing: list[str] = []
    for raw_concept in raw_concepts:
        if not isinstance(raw_concept, dict):
            continue
        label = str(raw_concept.get("label") or "").strip()
        normalized_label = _normalized_legal_reference(label)
        if not normalized_label or normalized_label in normalized_answer:
            continue
        terms = {
            token
            for token in re.findall(r"[0-9a-z]+", normalized_label)
            if len(token) >= 2
            and token not in _ANSWER_CONCEPT_GENERIC_TERMS
        }
        if not terms:
            continue
        matched = sum(
            re.search(rf"\b{re.escape(term)}\b", normalized_answer) is not None
            for term in terms
        )
        if matched < min(2, len(terms)):
            missing.append(label)
    if missing:
        raise _AnswerCoverageError(
            "Câu trả lời chưa giải quyết đúng khái niệm bắt buộc: "
            + ", ".join(missing)
        )


def _citation_response_schema(allowed_ids: list[str]) -> dict[str, Any]:
    """Constrain one model response to grounded, individually cited claims."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["statements"],
        "properties": {
            "statements": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["text", "citations"],
                    "properties": {
                        "text": {"type": "string"},
                        "citations": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "string",
                                "enum": allowed_ids,
                            },
                        },
                    },
                },
            }
        },
    }


def _render_citation_statements(
    structured: dict[str, Any],
    allowed_ids: list[str],
    *,
    sources: list[dict[str, Any]] | None = None,
) -> str:
    """Render schema-constrained claims with a citation on every sentence."""

    normalized_statements: list[dict[str, Any]] = []
    for raw_statement in structured.get("statements", []):
        text = str(raw_statement.get("text") or "")
        # The schema's citations array is authoritative. Gemini occasionally
        # repeats a citation in text, including malformed tails such as
        # ``[S3.``. Remove both complete and truncated copies before validating
        # and rendering the selected IDs ourselves.
        text = re.sub(
            r"\s*,?\s*\[\s*S\d+(?:\s*[,;]\s*S\d+)*\s*\]",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*,?\s*\[\s*S\d+\s*(?=$|[.,;:!?])",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        normalized_statements.append(
            {
                "text": text,
                "citations": raw_statement.get("citations", []),
            }
        )
    normalized = {"statements": normalized_statements}
    validate_citations(normalized, allowed_ids)
    sources_by_id = {
        str(source.get("source_id") or "").strip().upper(): source
        for source in sources or []
    }
    rendered_units: list[str] = []
    for statement in normalized["statements"]:
        citations = list(
            dict.fromkeys(
                str(item).strip().upper()
                for item in statement["citations"]
            )
        )
        suffix = " ".join(f"[{item}]" for item in citations)
        text = str(statement["text"])
        text = re.sub(r"\s+([,.!?;:])", r"\1", text)
        for unit in re.split(r"(?<=[.!?;])\s+|\n+", text):
            unit = unit.strip()
            if not unit:
                continue
            terminal = unit[-1] if unit[-1] in ".!?;" else ""
            body = unit[:-1].rstrip() if terminal else unit
            if sources is not None and not rendered_units:
                if not body.lstrip().startswith("Theo "):
                    source = sources_by_id.get(citations[0])
                    if source is not None:
                        body = f"Theo {format_source_locator(source)}, {body}"
                prefix = ""
            else:
                prefix = "- "
            rendered_units.append(f"{prefix}{body} {suffix}{terminal}")
    if not rendered_units:
        raise GeminiError("Gemini không trả về nhận định pháp lý có trích dẫn.")
    return "\n".join(rendered_units)


async def _complete_with_citation_repair(
    ai: GeminiService,
    system: str,
    prompt: str,
    *,
    allowed_ids: list[str],
    sources: list[dict[str, Any]] | None = None,
    answer_plan: dict[str, Any] | None = None,
    max_tokens: int,
    temperature: float = 0.1,
    thinking_budget: int | None = None,
    structured_initial: bool = False,
    skip_soft_repair: bool = False,
    generation_timeout: float | None = None,
    citation_repair_timeout: float | None = None,
    telemetry: dict[str, Any] | None = None,
) -> str:
    operation_started = time.perf_counter()
    log_progress(
        logger,
        "answer_generation",
        "draft_started",
        operation_started,
        generation_timeout=generation_timeout,
        source_count=len(allowed_ids),
        thinking_budget=thinking_budget or 0,
    )
    if telemetry is not None:
        telemetry["citation_repair_called"] = False
        telemetry["generation_initial_ms"] = 0.0
        telemetry["citation_normalize_ms"] = 0.0
        telemetry["citation_repair_ms"] = 0.0

    async def _generate_initial_answer() -> str:
        if structured_initial:
            structured = await ai.complete_json(
                system,
                prompt,
                schema=_citation_response_schema(allowed_ids),
                max_tokens=max_tokens,
                temperature=temperature,
                thinking_budget=thinking_budget,
            )
            return _render_citation_statements(
                structured,
                allowed_ids,
                sources=sources,
            )
        return await ai.complete(
            system,
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking_budget=thinking_budget,
        )

    try:
        if generation_timeout and generation_timeout > 0:
            async with asyncio.timeout(generation_timeout):
                answer = await _generate_initial_answer()
        else:
            answer = await _generate_initial_answer()
    except Exception as _te:
        gen_ms = round((time.perf_counter() - operation_started) * 1000, 1)
        if telemetry is not None:
            telemetry["failed_stage"] = "generation_initial"
            telemetry["exception_type"] = type(_te).__name__
            telemetry["timeout_configured"] = generation_timeout or 0.0
            telemetry["elapsed_actual_ms"] = gen_ms
            telemetry["generation_initial_ms"] = gen_ms
        if isinstance(_te, TimeoutError):
            raise GeminiError(
                f"Generation timed out after {generation_timeout:.1f}s"
            ) from _te
        raise

    gen_ms = round((time.perf_counter() - operation_started) * 1000, 1)
    if telemetry is not None:
        telemetry["generation_initial_ms"] = gen_ms

    log_progress(
        logger,
        "answer_generation",
        "draft_completed",
        operation_started,
        answer_chars=len(answer),
    )
    draft_safety_valid = False
    try:
        _validate_answer_safety(
            answer,
            allowed_ids=allowed_ids,
            sources=sources,
        )
        draft_safety_valid = True
        if sources is not None:
            _validate_professional_legal_opening(answer)
        _validate_answer_plan_coverage(answer, answer_plan)
        log_progress(
            logger,
            "answer_generation",
            "completed",
            operation_started,
            outcome="draft_valid",
        )
        return answer
    except GeminiError as draft_validation_exc:
        validation_kind = _answer_validation_kind(draft_validation_exc)

        # Attempt deterministic normalization before invoking expensive LLM repair!
        norm_start = time.perf_counter()
        normalized_draft = _normalize_citations_deterministically(answer, allowed_ids)
        norm_ms = round((time.perf_counter() - norm_start) * 1000, 1)
        if telemetry is not None:
            telemetry["citation_normalize_ms"] = norm_ms

        if normalized_draft != answer:
            try:
                _validate_answer_safety(
                    normalized_draft,
                    allowed_ids=allowed_ids,
                    sources=sources,
                )
                draft_safety_valid = True
                if sources is not None:
                    _validate_professional_legal_opening(normalized_draft)
                _validate_answer_plan_coverage(normalized_draft, answer_plan)
                log_progress(
                    logger,
                    "answer_generation",
                    "completed",
                    operation_started,
                    outcome="deterministic_normalization_valid",
                    validation_kind=validation_kind,
                )
                return normalized_draft
            except GeminiError:
                pass  # Deterministic normalization wasn't enough, continue to LLM repair

        if (
            draft_safety_valid
            and skip_soft_repair
            and validation_kind != "answer_plan_coverage"
        ):
            log_progress(
                logger,
                "answer_generation",
                "completed",
                operation_started,
                outcome="grounded_draft_retained",
                validation_kind=validation_kind,
            )
            return answer

        if telemetry is not None:
            telemetry["citation_repair_called"] = True

        log_progress(
            logger,
            "answer_generation",
            "citation_repair_started",
            operation_started,
            validation_kind=validation_kind,
        )
        repair_prompt = (
            f"{prompt}\n\n"
            "YÊU CẦU SỬA TRÍCH DẪN BẮT BUỘC:\n"
            "Chuyển câu trả lời thành các nhận định ngắn. Mỗi phần tử chỉ chứa "
            "một nhận định và phải chọn ít nhất một ID nguồn thực sự hỗ trợ "
            "nhận định đó. Không tạo ID mới. Chỉ được nhắc tên và số hiệu "
            "văn bản xuất hiện trong LEGAL_SOURCES. Với căn cứ điều khoản, "
            "viết theo mẫu: “Theo Điều ..., khoản ..., điểm ..., tên và số "
            "hiệu văn bản [Sx], ...”. Phần tử đầu tiên phải bắt đầu bằng “Theo”, "
            "nêu căn cứ và kết luận trực tiếp; không thêm lời chào hoặc tiêu đề. "
            "Chỉ viết ngày có hiệu lực khi trường effective_date có trong nguồn. "
            "Không suy diễn từ kiến thức nền.\n"
            "Phải giải quyết trực tiếp và đầy đủ mọi required_concepts trong "
            "ANSWER_PLAN; không thay bằng khái niệm rộng hoặc gần nghĩa. Khi "
            "nguồn có con số, tỷ lệ, điều kiện hay công thức trực tiếp, phải "
            "nêu và giải thích cách áp dụng.\n"
            f"{untrusted_data_block('DRAFT_WITH_INVALID_CITATIONS', answer)}"
        )
        repair_schema = _citation_response_schema(allowed_ids)
        _repair_timeout = citation_repair_timeout or 0
        repair_start = time.perf_counter()
        try:
            if _repair_timeout > 0:
                async with asyncio.timeout(_repair_timeout):
                    structured = await ai.complete_json(
                        system,
                        repair_prompt,
                        schema=repair_schema,
                        max_tokens=max_tokens,
                        temperature=0,
                        thinking_budget=thinking_budget,
                    )
            else:
                structured = await ai.complete_json(
                    system,
                    repair_prompt,
                    schema=repair_schema,
                    max_tokens=max_tokens,
                    temperature=0,
                    thinking_budget=thinking_budget,
                )
            repair_ms = round((time.perf_counter() - repair_start) * 1000, 1)
            if telemetry is not None:
                telemetry["citation_repair_ms"] = repair_ms
        except Exception as _cte:
            repair_ms = round((time.perf_counter() - repair_start) * 1000, 1)
            if telemetry is not None:
                telemetry["citation_repair_ms"] = repair_ms
                telemetry["failed_stage"] = "citation_repair"
                telemetry["exception_type"] = type(_cte).__name__
                telemetry["timeout_configured"] = _repair_timeout
                telemetry["elapsed_actual_ms"] = repair_ms
            logger.warning(
                "Citation repair timed out after %.1fs; retaining grounded draft",
                _repair_timeout,
            )
            if draft_safety_valid and validation_kind != "answer_plan_coverage":
                log_progress(
                    logger,
                    "answer_generation",
                    "completed",
                    operation_started,
                    outcome="citation_repair_timeout_draft_retained",
                )
                return answer
            if isinstance(_cte, TimeoutError):
                raise GeminiError(
                    f"Citation repair timed out after {_repair_timeout:.1f}s and draft was not grounded."
                ) from _cte
            raise
        log_progress(
            logger,
            "answer_generation",
            "citation_repair_response_received",
            operation_started,
        )
        repaired = _render_citation_statements(
            structured,
            allowed_ids,
            sources=sources,
        )
        try:
            _validate_answer_safety(
                repaired,
                allowed_ids=allowed_ids,
                sources=sources,
            )
        except Exception as repair_safety_exc:
            repair_validation_kind = _answer_validation_kind(
                repair_safety_exc
            )
            logger.warning(
                "Repaired answer safety validation failed "
                "validation_kind=%s draft_safety_valid=%s",
                repair_validation_kind,
                draft_safety_valid,
            )
            if draft_safety_valid and validation_kind != "answer_plan_coverage":
                log_progress(
                    logger,
                    "answer_generation",
                    "completed",
                    operation_started,
                    outcome="grounded_draft_fallback",
                    validation_kind=repair_validation_kind,
                )
                return answer
            raise GeminiError(
                "Không thể tạo câu trả lời có căn cứ và trích dẫn hợp lệ."
            ) from repair_safety_exc

        soft_validation_failures: list[str] = []
        if sources is not None:
            try:
                _validate_professional_legal_opening(repaired)
            except GeminiError as opening_exc:
                soft_validation_failures.append(
                    _answer_validation_kind(opening_exc)
                )
        try:
            _validate_answer_plan_coverage(repaired, answer_plan)
        except _AnswerCoverageError as coverage_exc:
            soft_validation_failures.append(
                _answer_validation_kind(coverage_exc)
            )
        if "answer_plan_coverage" in soft_validation_failures:
            raise GeminiError(
                "Câu trả lời đã sửa vẫn chưa giải quyết đúng khái niệm được hỏi."
            )
        if soft_validation_failures:
            logger.warning(
                "Repaired answer retained after soft validation "
                "validation_kinds=%s",
                ",".join(dict.fromkeys(soft_validation_failures)),
            )
        log_progress(
            logger,
            "answer_generation",
            "completed",
            operation_started,
            outcome=(
                "citation_repaired_with_warning"
                if soft_validation_failures
                else "citation_repaired"
            ),
            validation_kind=(
                ",".join(dict.fromkeys(soft_validation_failures))
                if soft_validation_failures
                else "none"
            ),
        )
        return repaired
    except Exception as exc:
        logger.warning(
            "Citation validation failed closed error_type=%s draft_safety_valid=%s",
            type(exc).__name__,
            draft_safety_valid,
        )
        if draft_safety_valid and validation_kind != "answer_plan_coverage":
            log_progress(
                logger,
                "answer_generation",
                "completed",
                operation_started,
                outcome="grounded_draft_fallback",
            )
            return answer
        raise GeminiError(
            "Không thể xác minh căn cứ của câu trả lời."
        ) from exc


async def _load_postgres_chat_history(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    settings: Settings,
    *,
    limit: int = 12,
    before_sequence: int | None = None,
) -> list[tuple[str, str]]:
    """Load persisted history from PostgreSQL in chronological order."""
    filters = [
        ChatMessage.conversation_id == conversation_id,
        ChatMessage.status == "COMPLETED",
    ]
    if before_sequence is not None:
        filters.append(ChatMessage.message_sequence < before_sequence)
    stored_messages = (
        await db.scalars(
            select(ChatMessage)
            .where(*filters)
            .order_by(ChatMessage.message_sequence.desc())
            .limit(limit)
        )
    ).all()
    history: list[tuple[str, str]] = []
    for message in reversed(stored_messages):
        content = decrypt_text(message.content_ciphertext, settings)
        attachment_payloads = _stored_attachment_payloads(message, settings)
        if attachment_payloads:
            content = (
                f"{content}\n\nTệp đính kèm của lượt này:\n"
                f"{compact_attachment_context(attachment_payloads)}"
            )
        history.append((message.role, content))
    return history


@router.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
async def readiness(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    ai: GeminiService = Depends(ai_service),
    embeddings: VertexAIEmbeddingService = Depends(embedding_service),
) -> dict[str, str]:
    try:
        await db.scalar(select(func.now()))
        await db.rollback()
    except Exception as exc:
        logger.warning("Database readiness check failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database connection is not ready",
        ) from exc
    if not settings.embedding_ready:
        raise HTTPException(
            status_code=503,
            detail="Vertex AI embedding configuration is not ready",
        )
    if settings.require_freshness_check and not settings.tavily_ready:
        raise HTTPException(
            status_code=503,
            detail="Legal freshness verification is not configured",
        )
    try:
        await run_in_threadpool(embeddings.ensure_ready)
    except Exception as exc:
        logger.warning(
            "Vertex AI embedding readiness failed error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Vertex AI embedding service is not ready",
        ) from exc
    try:
        await ai.ensure_ready()
    except Exception as exc:
        logger.warning(
            "Gemini readiness failed error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Gemini service is not ready",
        ) from exc
    return {"status": "ready"}


@router.get("/stats")
async def stats(
    db: AsyncSession = Depends(get_db),
    retrieval: RetrievalService = Depends(retrieval_service),
) -> dict[str, Any]:
    raw = await retrieval.stats()
    return {
        "documents": int(raw.get("documents", 0) or 0),
        "nodes": int(raw.get("nodes", 0) or 0),
        "edges": int(raw.get("edges", 0) or 0),
        "chunks": int(raw.get("chunks", 0) or 0),
        "conversations": int(await db.scalar(select(func.count(Conversation.id))) or 0),
        "artifacts": int(await db.scalar(select(func.count(Artifact.id))) or 0),
        "answer_cache_entries": int(
            await db.scalar(
                select(func.count(LegalAnswerCache.id)).where(
                    LegalAnswerCache.expires_at > datetime.now(UTC)
                )
            )
            or 0
        ),
        "answer_cache_hits": int(
            await db.scalar(select(func.coalesce(func.sum(LegalAnswerCache.hit_count), 0)))
            or 0
        ),
        "retrieval_policy": "Tự động áp dụng toàn bộ kho luật; kiểm tra hiệu lực trước mỗi câu trả lời",
    }


@router.get("/templates")
async def templates() -> dict[str, Any]:
    return {"items": CONTRACT_TEMPLATES, "categories": sorted({item["category"] for item in CONTRACT_TEMPLATES})}


@router.get("/laws")
async def laws(
    q: str = "",
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
) -> dict[str, Any]:
    statement = select(LegalDocument).order_by(LegalDocument.verified_at.desc().nullslast(), LegalDocument.title)
    if q.strip():
        like = f"%{q.strip()}%"
        statement = statement.where((LegalDocument.code.ilike(like)) | (LegalDocument.title.ilike(like)))
    rows = (await db.scalars(statement.limit(limit))).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "code": row.code,
                "title": row.title,
                "status": row.status,
                "source_url": row.source_url,
                "verified_at": row.verified_at,
                "version": row.version,
            }
            for row in rows
        ]
    }


_NORMALIZED_LAW_CODE_SQL = """
upper(
    regexp_replace(
        btrim({value}),
        '[[:space:]]+',
        '',
        'g'
    )
)
"""


@router.get("/laws/detail", response_model=LegalDocumentDetailOut)
async def law_detail(
    code: str = Query(min_length=3, max_length=120),
    citation: str = Query(default="", max_length=1000),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(current_user),
) -> LegalDocumentDetailOut:
    """Return indexed evidence for a citation without guessing a public URL."""

    normalized_code = _NORMALIZED_LAW_CODE_SQL.format(value=":code")
    document_code = _NORMALIZED_LAW_CODE_SQL.format(value="document.code")
    metadata_statement = sql_text(
        f"""
        SELECT
            corpus.code,
            coalesce(nullif(document.title, ''), corpus.title) AS title,
            corpus.document_type,
            coalesce(document.issuer, '') AS issuer,
            coalesce(nullif(document.source_url, ''), nullif(corpus.source_url, ''))
                AS source_url,
            CASE
                WHEN document.verified_at IS NOT NULL
                 AND upper(coalesce(document.status, '')) NOT IN (
                    '', 'UNKNOWN', 'UNVERIFIED'
                 )
                    THEN upper(document.status)
                ELSE corpus.corpus_status
            END AS status,
            corpus.law_version
        FROM legal_catalog_corpus AS corpus
        LEFT JOIN legal_document AS document
          ON {document_code} = corpus.law_code_normalized
        WHERE corpus.law_code_normalized = {normalized_code}
        LIMIT 1
        """
    )
    metadata = (
        await db.execute(metadata_statement, {"code": code})
    ).mappings().first()
    if metadata is None:
        raise HTTPException(
            status_code=404,
            detail="KhÃ´ng tÃ¬m tháº¥y vÄƒn báº£n trong kho dá»¯ liá»‡u.",
        )

    chunk_code = _NORMALIZED_LAW_CODE_SQL.format(value="chunk.law_code")
    focus = citation.strip()
    focus_filter = """
      AND (
        lower(btrim(chunk.citation)) = lower(btrim(:citation))
        OR lower(btrim(chunk.path_label)) = lower(btrim(:citation))
      )
    """ if focus else ""
    current_chunks = f"""
        FROM graphrag_chunk AS chunk
        INNER JOIN graphrag_law_version AS latest_law
          ON latest_law.law_code_normalized = {chunk_code}
         AND latest_law.latest_version = chunk.law_version
        WHERE {chunk_code} = {normalized_code}
        {focus_filter}
    """

    async def load_sections(use_focus: bool) -> tuple[list[Any], int]:
        active_chunks = current_chunks if use_focus else current_chunks.replace(
            focus_filter,
            "",
        )
        total = int(
            await db.scalar(
                sql_text(f"SELECT count(*) {active_chunks}"),
                {"code": code, "citation": focus},
            )
            or 0
        )
        offset = (page - 1) * page_size if not use_focus else 0
        limit = page_size if not use_focus else min(page_size, 20)
        rows = (
            await db.execute(
                sql_text(
                    f"""
                    SELECT
                        chunk.citation,
                        chunk.title,
                        chunk.path_label,
                        chunk.text,
                        chunk.chunk_type,
                        chunk.ordinal
                    {active_chunks}
                    ORDER BY chunk.ordinal
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {
                    "code": code,
                    "citation": focus,
                    "limit": limit,
                    "offset": offset,
                },
            )
        ).mappings().all()
        return list(rows), total

    rows, total = await load_sections(bool(focus))
    focused = bool(focus and rows)
    if focus and not rows:
        rows, total = await load_sections(False)

    return LegalDocumentDetailOut(
        code=str(metadata["code"]),
        title=str(metadata["title"]),
        document_type=str(metadata["document_type"]),
        issuer=str(metadata["issuer"]),
        status=str(metadata["status"]),
        source_url=(
            str(metadata["source_url"])
            if metadata["source_url"]
            else None
        ),
        law_version=(
            int(metadata["law_version"])
            if metadata["law_version"] is not None
            else None
        ),
        focused=focused,
        sections=[LegalDocumentSectionOut.model_validate(row) for row in rows],
        total=total,
        page=1 if focused else page,
        page_size=min(page_size, 20) if focused else page_size,
    )


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(
    payload: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> ConversationOut:
    conversation = Conversation(
        user_id=user.id,
        title=payload.title,
        retrieval_mode=settings.retriever_backend.upper(),
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return _conversation_out(conversation)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    status_filter: str = Query("ACTIVE", alias="status"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[ConversationOut]:
    statement = (
        select(Conversation, func.count(ChatMessage.id))
        .outerjoin(
            ChatMessage,
            and_(
                ChatMessage.conversation_id == Conversation.id,
                ChatMessage.status == "COMPLETED",
            ),
        )
        .where(Conversation.user_id == user.id, Conversation.status == status_filter.upper())
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    return [_conversation_out(row, int(count)) for row, count in (await db.execute(statement)).all()]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> ConversationDetailOut:
    conversation = await _owned_conversation(db, conversation_id, user)
    message_rows = (
        await db.execute(
            select(ChatMessage, ChatAnswerFeedback.rating)
            .outerjoin(
                ChatAnswerFeedback,
                ChatAnswerFeedback.message_id == ChatMessage.id,
            )
            .where(
                ChatMessage.conversation_id == conversation.id,
                ChatMessage.status == "COMPLETED",
            )
            .order_by(ChatMessage.message_sequence)
        )
    ).all()
    messages = [
        _message_out(message, settings, feedback_rating)
        for message, feedback_rating in message_rows
    ]
    await _enrich_stored_source_urls(db, messages)
    return ConversationDetailOut(
        conversation=_conversation_out(conversation, len(message_rows)),
        messages=messages,
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> ConversationOut:
    conversation = await _owned_conversation(db, conversation_id, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(conversation, field, value)
    await db.commit()
    await db.refresh(conversation)
    return _conversation_out(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    conversation = await _owned_conversation(db, conversation_id, user)
    await db.delete(conversation)
    await db.commit()
    return Response(status_code=204)


@router.put(
    "/chat/messages/{message_id}/feedback",
    response_model=ChatAnswerFeedbackOut,
)
async def rate_chat_answer(
    message_id: uuid.UUID,
    payload: ChatAnswerFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> ChatAnswerFeedbackOut:
    if (
        payload.rating == "bad"
        and (payload.comment is None or len(payload.comment) < 3)
    ):
        raise HTTPException(
            status_code=422,
            detail="Vui lòng cho biết câu trả lời cần cải thiện điều gì",
        )

    answer_message, question_message = await _owned_feedback_target(
        db,
        message_id,
        user.id,
    )
    question = _message_content_out(question_message, settings)
    answer = _message_content_out(answer_message, settings)
    feedback = await db.scalar(
        select(ChatAnswerFeedback).where(
            ChatAnswerFeedback.message_id == message_id
        )
    )
    if feedback is None:
        feedback = ChatAnswerFeedback(
            user_id=user.id,
            conversation_id=answer_message.conversation_id,
            message_id=message_id,
            rating=payload.rating.upper(),
            question_ciphertext=encrypt_text(question, settings),
            answer_ciphertext=encrypt_text(answer, settings),
        )
        db.add(feedback)
    else:
        feedback.rating = payload.rating.upper()
        feedback.question_ciphertext = encrypt_text(question, settings)
        feedback.answer_ciphertext = encrypt_text(answer, settings)
        feedback.regenerated_message_id = None
    feedback.comment_ciphertext = (
        encrypt_text(payload.comment, settings)
        if payload.comment
        else None
    )
    await db.commit()
    return ChatAnswerFeedbackOut(
        message_id=message_id,
        rating=payload.rating,
        regeneration_available=payload.rating == "bad",
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    retrieval: RetrievalService = Depends(retrieval_service),
    freshness: LegalFreshnessService = Depends(freshness_service),
    ai: GeminiService = Depends(ai_service),
    memory: ConversationMemoryService = Depends(conversation_memory_service),
    answer_cache: SemanticAnswerCacheService = Depends(semantic_answer_cache_service),
    response: Response = None,
) -> ChatResponse:
    request_id = current_request_id()

    timings: dict[str, float] = {
        "auth": 0.0,
        "context": 0.0,
        "routing": 0.0,
        "cache": 0.0,
        "rewrite": 0.0,
        "structure": 0.0,
        "retrieval": 0.0,
        "evidence_gate": 0.0,
        "freshness": 0.0,
        "generation_initial": 0.0,
        "citation_normalize": 0.0,
        "citation_repair": 0.0,
        "persistence": 0.0,
        "total": 0.0,
    }
    telemetry_details: dict[str, Any] = {
        "failed_stage": "none",
        "exception_type": "none",
        "timeout_configured": 0.0,
        "elapsed_actual_ms": 0.0,
        "citation_repair_called": False,
    }
    generation_fallback = False

    t_auth0 = time.perf_counter()
    authenticated_user_id = user.id
    preferred_name = user.preferred_name
    if not preferred_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vui lòng chọn tên gọi trước khi bắt đầu trò chuyện",
        )
    timings["auth"] = round((time.perf_counter() - t_auth0) * 1000, 1)

    current_question = payload.message
    regeneration_target_id = payload.regenerate_from_message_id
    if regeneration_target_id and payload.attachments:
        raise HTTPException(
            status_code=422,
            detail="Không thể thay tệp đính kèm khi đang tạo lại câu trả lời",
        )
    attachment_payloads = (
        _request_attachment_payloads(
            payload.attachments,
            authenticated_user_id,
            settings,
        )
        if not regeneration_target_id
        else []
    )
    message_attachments = [
        attachment_metadata(item)
        for item in attachment_payloads
    ]
    regeneration_feedback = ""
    regeneration_original_answer = ""
    regeneration_feedback_id: uuid.UUID | None = None
    regeneration_question_sequence: int | None = None
    if regeneration_target_id and payload.conversation_id is None:
        raise HTTPException(
            status_code=422,
            detail="Cần có cuộc trò chuyện để tạo lại câu trả lời",
        )

    operation_started = time.perf_counter()
    context_started = time.perf_counter()
    processing_profile = chat_profile_for_route("single_hop")
    conversation: Conversation | None = None
    conversation_id: uuid.UUID | None = None
    is_new_conversation = payload.conversation_id is None
    log_progress(
        logger,
        "chat",
        "started",
        operation_started,
        authenticated=True,
        has_conversation_id=bool(payload.conversation_id),
        history_turn_count=0,
    )
    cache_scope = f"user:{authenticated_user_id}:auto-route-v1"
    summary_context = ""
    history_turns: list[tuple[str, str]] = []
    greeting_answer = (
        None
        if regeneration_target_id or attachment_payloads
        else greeting_response(current_question, preferred_name)
    )
    if payload.conversation_id:
        conversation = await _owned_conversation(db, payload.conversation_id, user)
        conversation_id = conversation.id
        if regeneration_target_id:
            answer_message, question_message = await _owned_feedback_target(
                db,
                regeneration_target_id,
                authenticated_user_id,
            )
            if answer_message.conversation_id != conversation_id:
                raise HTTPException(
                    status_code=404,
                    detail="Câu trả lời không thuộc cuộc trò chuyện này",
                )
            stored_feedback = await db.scalar(
                select(ChatAnswerFeedback).where(
                    ChatAnswerFeedback.message_id == regeneration_target_id,
                    ChatAnswerFeedback.user_id == authenticated_user_id,
                    ChatAnswerFeedback.rating == "BAD",
                )
            )
            if (
                stored_feedback is None
                or not stored_feedback.comment_ciphertext
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Hãy gửi góp ý trước khi tạo lại câu trả lời",
                )
            current_question = _message_content_out(
                question_message,
                settings,
            )
            attachment_payloads = _stored_attachment_payloads(
                question_message,
                settings,
            )
            message_attachments = list(
                getattr(question_message, "attachments", []) or []
            )
            regeneration_original_answer = _message_content_out(
                answer_message,
                settings,
            )
            regeneration_feedback = decrypt_text(
                stored_feedback.comment_ciphertext,
                settings,
            )
            regeneration_feedback_id = stored_feedback.id
            regeneration_question_sequence = (
                question_message.message_sequence
            )
            history_turns = await _load_postgres_chat_history(
                db,
                conversation_id,
                settings,
                before_sequence=regeneration_question_sequence,
            )
        elif greeting_answer is None:
            summary_context = await memory.get_summary(db, conversation_id)
            history_turns = await _load_postgres_chat_history(
                db,
                conversation_id,
                settings,
            )
    approved_examples = (
        await _load_approved_answer_examples(
            db,
            authenticated_user_id,
            current_question,
            settings,
        )
        if greeting_answer is None
        else []
    )
    # Authentication and history reads must not retain a PostgreSQL
    # transaction while cache/search/Gemini network calls are in flight.
    await db.rollback()
    conversation = None
    invalidate_feedback_answer = getattr(
        answer_cache,
        "invalidate_feedback_answer",
        None,
    )
    if regeneration_target_id and callable(invalidate_feedback_answer):
        try:
            await invalidate_feedback_answer(
                current_question,
                regeneration_original_answer,
                scope=cache_scope,
            )
        except Exception:
            logger.exception(
                "Cannot invalidate answer cache after negative feedback"
            )

    log_progress(
        logger,
        "chat",
        "context_ready",
        operation_started,
        history_turn_count=len(history_turns),
        summary_available=bool(summary_context),
    )
    timings["context"] = round((time.perf_counter() - context_started) * 1000, 1)
    attachment_evidence_payloads = select_relevant_attachment_context(
        attachment_payloads,
        current_question,
    )
    attachment_fact_mode = bool(
        attachment_evidence_payloads
        and is_direct_attachment_question(current_question)
    )
    routing_started = time.perf_counter()
    catalog_answer: str | None = None
    guard_answer: str | None = None
    guard_cache_mode: str | None = None
    guard_verification: dict[str, Any] | None = None
    catalog_req = (
        parse_catalog_request(current_question)
        if greeting_answer is None and not attachment_payloads
        else None
    )
    if catalog_req is not None:
        try:
            catalog_service = LegalCatalogService(db)
            catalog_answer = await catalog_service.answer(catalog_req)
        except Exception as _cat_exc:
            logger.warning("Deterministic catalog lookup failed error=%s", _cat_exc)

    if greeting_answer is not None:
        retrieval_query = current_question
        answer_plan: dict[str, Any] = {}
        query_was_rewritten = False
        log_progress(
            logger,
            "chat",
            "greeting_completed",
            operation_started,
            outcome="deterministic_response",
        )
    elif catalog_answer is not None:
        retrieval_query = current_question
        answer_plan = {}
        query_was_rewritten = False
        log_progress(
            logger,
            "chat",
            "catalog_completed",
            operation_started,
            outcome="deterministic_catalog_response",
        )
    else:
        # --- Prompt injection and Out-of-Scope guards (Python layer) ---
        injection_block = _check_prompt_injection(current_question)
        if injection_block is not None:
            guard_answer = injection_block
            guard_cache_mode = "injection_blocked"
            guard_verification = VerificationReport(
                checked=False,
                all_current=False,
                checked_at=datetime.now(UTC),
                items=[],
                note="injection_blocked",
            ).model_dump(mode="json")
            retrieval_query = current_question
            answer_plan = {}
            query_was_rewritten = False
        else:
            scope_block = _check_non_labor_scope(current_question)
            if scope_block is not None:
                guard_answer = scope_block
                guard_cache_mode = "out_of_scope"
                guard_verification = VerificationReport(
                    checked=False,
                    all_current=False,
                    checked_at=datetime.now(UTC),
                    items=[],
                    note="out_of_scope_non_labor",
                ).model_dump(mode="json")
                retrieval_query = current_question
                answer_plan = {}
                query_was_rewritten = False
            elif attachment_fact_mode:
                retrieval_query = current_question
                answer_plan = {}
                query_was_rewritten = False
                log_progress(
                    logger,
                    "chat",
                    "attachment_fact_route_selected",
                    operation_started,
                    attachment_count=len(attachment_evidence_payloads),
                )
            else:
                rewrite_started = time.perf_counter()
                log_progress(logger, "chat", "query_rewrite_started", operation_started)
                rewrite_triggered = should_rewrite_query(current_question)
                if not rewrite_triggered:
                    retrieval_query = current_question
                    query_was_rewritten = False
                    rewrite_attempted = False
                else:
                    query_rewrite = await rewrite_query_if_needed(
                        ai,
                        current_question,
                        history=history_turns,
                        settings=settings,
                    )
                    retrieval_query = query_rewrite.retrieval_query
                    query_was_rewritten = query_rewrite.rewritten
                    rewrite_attempted = query_rewrite.attempted
                retrieval_query = _retrieval_query_with_attachments(
                    retrieval_query,
                    attachment_evidence_payloads,
                )
                answer_plan = build_answer_plan(retrieval_query)
                log_progress(
                    logger,
                    "chat",
                    "query_rewrite_completed",
                    operation_started,
                    attempted=rewrite_attempted,
                    phase_ms=round((time.perf_counter() - rewrite_started) * 1000),
                    rewritten=query_was_rewritten,
                    trigger_detected=rewrite_triggered,
                )
                timings["rewrite"] = round(
                    (time.perf_counter() - rewrite_started) * 1000,
                    1,
                )

    retrieval_route = classify_retrieval_route(retrieval_query)
    processing_profile = chat_profile_for_route(retrieval_route)
    log_progress(
        logger,
        "chat",
        "automatic_route_selected",
        operation_started,
        route=retrieval_route,
    )

    timings["routing"] = max(
        0.0,
        round(
            (time.perf_counter() - routing_started) * 1000
            - timings["rewrite"],
            1,
        ),
    )

    structure_result: dict[str, Any] | None = None
    structure_lookup = getattr(
        retrieval,
        "lookup_document_structure",
        None,
    )
    structure_started = time.perf_counter()
    if (
        greeting_answer is None
        and catalog_answer is None
        and guard_answer is None
        and not attachment_payloads
        and callable(structure_lookup)
    ):
        structure_result = await structure_lookup(retrieval_query)
        if structure_result is not None:
            log_progress(
                logger,
                "chat",
                "structure_answer_completed",
                operation_started,
                outcome="deterministic_graph_count",
            )
    timings["structure"] = round(
        (time.perf_counter() - structure_started) * 1000,
        1,
    )

    cache_lookup: CacheLookup | None = None
    cache_hit = False
    cache_similarity: float | None = None
    cache_mode = guard_cache_mode or "miss"
    cached_draft = ""
    answer = (
        greeting_answer
        or catalog_answer
        or guard_answer
        or str((structure_result or {}).get("answer") or "")
    )
    structure_source = (structure_result or {}).get("source")
    sources: list[dict[str, Any]] = (
        [structure_source]
        if isinstance(structure_source, dict)
        else []
    )
    if catalog_answer is not None:
        verification = VerificationReport(
            checked=True,
            all_current=True,
            checked_at=datetime.now(UTC),
            items=[],
            note="catalog_deterministic",
        ).model_dump(mode="json")
    elif guard_verification is not None:
        verification = guard_verification
    elif structure_result is not None:
        verification = VerificationReport(
            checked=False,
            all_current=False,
            checked_at=datetime.now(UTC),
            items=[],
            note=(
                "Số liệu được thống kê trực tiếp từ phiên bản văn bản đã "
                "được lập chỉ mục."
            ),
        ).model_dump(mode="json")
    else:
        verification = (
            VerificationReport().model_dump(mode="json")
            if greeting_answer is not None
            else {}
        )
    answer_ready = (
        greeting_answer is not None
        or catalog_answer is not None
        or guard_answer is not None
        or structure_result is not None
    )
    cache_eligible = (
        not answer_ready
        and not attachment_payloads
        and answer_cache.eligible(
            current_question,
            has_conversation_context=bool(history_turns or summary_context),
        )
        and regeneration_target_id is None
    )
    cache_lookup_started = time.perf_counter()
    log_progress(
        logger,
        "chat",
        "cache_lookup_started",
        operation_started,
        eligible=cache_eligible,
    )
    if cache_eligible:
        try:
            exact_lookup = getattr(answer_cache, "lookup_exact", None)
            if retrieval_route == "single_hop" and callable(exact_lookup):
                cache_lookup = await exact_lookup(
                    retrieval_query,
                    scope=cache_scope,
                )
            else:
                cache_lookup = await answer_cache.lookup(
                    retrieval_query,
                    scope=cache_scope,
                )
        except Exception:
            logger.exception("Cannot query semantic answer cache")
    log_progress(
        logger,
        "chat",
        "cache_lookup_completed",
        operation_started,
        candidate_found=bool(cache_lookup and cache_lookup.hit),
        phase_ms=round((time.perf_counter() - cache_lookup_started) * 1000),
    )
    timings["cache"] = round(
        (time.perf_counter() - cache_lookup_started) * 1000,
        1,
    )

    if cache_lookup and cache_lookup.hit:
        cached = cache_lookup.hit
        try:
            if not cached.sources:
                raise GeminiError("Bản cache không có nguồn pháp lý.")
            validate_citations(
                cached.answer,
                [source.get("source_id", "") for source in cached.sources],
                require_claim_coverage=True,
            )
            _validate_answer_plan_coverage(cached.answer, answer_plan)
            current_sources, current_verification = await _legal_sources(
                retrieval_query,
                retrieval,
                freshness,
                allow_empty=True,
                telemetry=timings,
            )
            fingerprint_matches = (
                legal_fingerprint(current_sources, current_verification)
                == cached.law_fingerprint
            )
            if (
                current_verification.get("checked")
                and current_verification.get("all_current")
                and fingerprint_matches
            ):
                validate_citations(
                    cached.answer,
                    [source.get("source_id", "") for source in current_sources],
                    require_claim_coverage=True,
                )
                sources = current_sources
                verification = current_verification
                cache_similarity = cached.similarity
                if cached.exact_match:
                    answer = cached.answer
                    cache_hit = True
                    answer_ready = True
                    cache_mode = "exact"
                else:
                    cached_draft = cached.answer
                    cache_mode = "semantic_draft"
                try:
                    await answer_cache.record_hit(cached.id)
                except Exception:
                    logger.exception("Cannot update semantic answer cache hit counter")
            else:
                sources = current_sources
                verification = current_verification
                await answer_cache.invalidate(cached.id)
        except HTTPException:
            try:
                await answer_cache.invalidate(cached.id)
            except Exception:
                logger.exception(
                    "Cannot invalidate semantic answer cache entry %s",
                    cached.id,
                )
            raise
        except Exception:
            logger.exception("Cannot validate semantic answer cache entry %s", cached.id)
            try:
                await answer_cache.invalidate(cached.id)
            except Exception:
                logger.exception("Cannot invalidate semantic answer cache entry %s", cached.id)

    if not answer_ready:
        if attachment_fact_mode:
            sources = _attachment_citation_sources(
                attachment_evidence_payloads,
                start_index=1,
            )
            verification = VerificationReport(
                checked=False,
                all_current=False,
                checked_at=datetime.now(UTC),
                items=[],
                note="user_attachment_factual",
            ).model_dump(mode="json")
        else:
            data_unavailable = (
                not sources
                and verification.get("note") == LEGAL_DATA_UNAVAILABLE_MESSAGE
            )
            if not sources and not data_unavailable:
                sources, verification = await _legal_sources(
                    retrieval_query,
                    retrieval,
                    freshness,
                    allow_empty=True,
                    telemetry=timings,
                )
            if (
                sources
                and retrieval_route == "single_hop"
                and not attachment_payloads
            ):
                sources, verification, gated_query = await _evidence_gated_sources(
                    original_question=current_question,
                    retrieval_query=retrieval_query,
                    sources=sources,
                    verification=verification,
                    ai=ai,
                    retrieval=retrieval,
                    freshness=freshness,
                    settings=settings,
                    telemetry=timings,
                )
                if gated_query != retrieval_query:
                    retrieval_query = gated_query
                    answer_plan = build_answer_plan(retrieval_query)
        if attachment_evidence_payloads and not attachment_fact_mode:
            sources = [
                *sources,
                *_attachment_citation_sources(
                    attachment_evidence_payloads,
                    start_index=len(sources) + 1,
                ),
            ]
        if not sources:
            answer = LEGAL_DATA_UNAVAILABLE_MESSAGE
            log_progress(
                logger,
                "chat",
                "answer_completed",
                operation_started,
                outcome="data_unavailable",
                source_count=0,
            )
        else:
            log_progress(
                logger,
                "chat",
                "answer_generation_started",
                operation_started,
                source_count=len(sources),
            )
            generation_started = time.perf_counter()
            _gen_timeout = (
                settings.legal_chat_fast_timeout_seconds
                if retrieval_route == "single_hop"
                else settings.legal_chat_generation_timeout_seconds
            )
            _repair_timeout = settings.legal_chat_citation_repair_timeout_seconds
            generation_system = (
                ATTACHMENT_QA_SYSTEM_PROMPT
                if attachment_fact_mode
                else LEGAL_SYSTEM_PROMPT
            )
            context_sources = compact_context_sources(
                sources,
                retrieval_query,
                max_chars=(
                    12_000
                    if attachment_fact_mode
                    else (6_000 if retrieval_route == "single_hop" else 9_000)
                ),
                per_source_chars=(
                    7_000
                    if attachment_fact_mode
                    else (1_000 if retrieval_route == "single_hop" else 1_200)
                ),
            )
            try:
                answer = await _complete_with_citation_repair(
                    ai,
                    generation_system,
                    "BỘ NHỚ TÓM TẮT:\n"
                    f"{_summary_prompt(summary_context)}\n\n"
                    f"LỊCH SỬ HỘI THOẠI GẦN ĐÂY:\n{_chat_history_prompt(history_turns)}\n\n"
                    "KẾ HOẠCH PHỦ CÂU HỎI:\n"
                    f"{untrusted_data_block('ANSWER_PLAN', answer_plan)}\n\n"
                    f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\n"
                    f"NGUỒN:\n{build_context(context_sources)}\n\n"
                    "TỆP ĐÍNH KÈM DO NGƯỜI DÙNG CUNG CẤP:\n"
                    f"{untrusted_data_block('USER_ATTACHMENTS', attachment_evidence_payloads) if attachment_evidence_payloads else '(Không có)'}\n\n"
                    f"CÂU HỎI HIỆN TẠI:\n{untrusted_data_block('CURRENT_QUESTION', current_question)}"
                    "\n\nCÁCH HIỂU ĐÃ CHUẨN HÓA:\n"
                    f"{untrusted_data_block('REWRITTEN_QUERY', retrieval_query) if query_was_rewritten else '(Không cần chuẩn hóa)'}"
                    "\n\nVÍ DỤ ĐÃ ĐƯỢC NGƯỜI DÙNG ĐÁNH GIÁ TỐT:\n"
                    f"{untrusted_data_block('APPROVED_ANSWER_EXAMPLES', approved_examples) if approved_examples else '(Không có)'}\n"
                    "Chỉ học cách tổ chức, mức độ rõ ràng và phong cách trình bày từ ví dụ tốt. "
                    "Không sao chép dữ kiện hay mã nguồn của ví dụ; mọi kết luận hiện tại phải dựa trên NGUỒN đang được cấp.\n"
                    "\nPHẢN HỒI CẦN SỬA Ở LẦN TRẢ LỜI TRƯỚC:\n"
                    f"{untrusted_data_block('REGENERATION_FEEDBACK', {'previous_answer': regeneration_original_answer, 'human_feedback': regeneration_feedback}) if regeneration_target_id else '(Không có)'}\n"
                    "Nếu có phản hồi, hãy tạo một câu trả lời mới giải quyết trực tiếp góp ý, "
                    "không nhắc đến quy trình đánh giá hoặc việc đang tạo lại câu trả lời.\n"
                    f"\n\nBẢN NHÁP CACHE THAM KHẢO:\n"
                    f"{untrusted_data_block('CACHE_DRAFT', cached_draft) if cached_draft else '(Không có)'}\n"
                    "Nếu có bản nháp, phải điều chỉnh theo đúng câu hỏi hiện tại; "
                    "không được sao chép các kết luận không còn phù hợp.",
                    allowed_ids=[source["source_id"] for source in sources],
                    sources=sources,
                    answer_plan=answer_plan,
                    max_tokens=processing_profile.max_output_tokens,
                    thinking_budget=processing_profile.thinking_budget,
                    structured_initial=(
                        attachment_fact_mode or retrieval_route == "single_hop"
                    ),
                    skip_soft_repair=(retrieval_route == "single_hop"),
                    generation_timeout=_gen_timeout,
                    citation_repair_timeout=_repair_timeout,
                    telemetry=telemetry_details,
                )
            except GeminiError as exc:
                generation_ms = round((time.perf_counter() - generation_started) * 1000)
                logger.warning(
                    "Chat generation unavailable error_type=%s error=%s "
                    "route=%s generation_ms=%d generation_timeout=%.1f",
                    type(exc).__name__,
                    str(exc)[:200],
                    retrieval_route,
                    generation_ms,
                    _gen_timeout,
                )
                # A transient Vertex retry must not erase already retrieved
                # legal evidence. Try once more with a compact, structured
                # prompt and no thinking budget before returning an outage
                # message. This path is intentionally source-grounded and is
                # useful for both narrative scenarios and ordinary lookups.
                rescue_sources = compact_context_sources(
                    sources,
                    retrieval_query,
                    max_chars=4_800,
                    per_source_chars=800,
                )[:6]
                rescue_timeout = max(12.0, min(20.0, _gen_timeout))
                try:
                    answer = await _complete_with_citation_repair(
                        ai,
                        generation_system,
                        "KẾ HOẠCH PHỦ CÂU HỎI:\n"
                        f"{untrusted_data_block('ANSWER_PLAN', answer_plan)}\n\n"
                        "KIỂM TRA HIỆU LỰC:\n"
                        f"{_verification_prompt(verification)}\n\n"
                        "NGUỒN TRỰC TIẾP:\n"
                        f"{build_context(rescue_sources)}\n\n"
                        "CÂU HỎI HIỆN TẠI:\n"
                        f"{untrusted_data_block('CURRENT_QUESTION', current_question)}\n\n"
                        "Hãy trả lời ngắn gọn nhưng đầy đủ trọng tâm. Với tình huống, "
                        "nêu kết luận có điều kiện, áp dụng vào dữ kiện và hành động thực tế; "
                        "không từ chối theo phạm vi khi nguồn đã được cung cấp.",
                        allowed_ids=[source["source_id"] for source in rescue_sources],
                        sources=rescue_sources,
                        answer_plan=answer_plan,
                        max_tokens=min(processing_profile.max_output_tokens, 1_800),
                        thinking_budget=0,
                        structured_initial=True,
                        skip_soft_repair=True,
                        generation_timeout=rescue_timeout,
                        citation_repair_timeout=_repair_timeout,
                        telemetry=telemetry_details,
                    )
                except GeminiError as rescue_exc:
                    logger.warning(
                        "Compact grounded generation also unavailable "
                        "error_type=%s error=%s timeout=%.1f",
                        type(rescue_exc).__name__,
                        str(rescue_exc)[:200],
                        rescue_timeout,
                    )
                    answer = AI_TEMPORARILY_UNAVAILABLE_MESSAGE
                    generation_fallback = True
                    sources = []
                    verification = VerificationReport(
                        checked=False,
                        all_current=False,
                        checked_at=datetime.now(UTC),
                        items=[],
                        note=AI_TEMPORARILY_UNAVAILABLE_MESSAGE,
                    ).model_dump(mode="json")
                    cache_mode = "miss"
                    log_progress(
                        logger,
                        "chat",
                        "answer_generation_fallback",
                        operation_started,
                        route=retrieval_route,
                        error_type=type(rescue_exc).__name__,
                        generation_ms=generation_ms,
                        outcome="ai_unavailable",
                    )
                else:
                    sources = rescue_sources
                    generation_ms = round(
                        (time.perf_counter() - generation_started) * 1000
                    )
                    log_progress(
                        logger,
                        "chat",
                        "answer_generation_completed",
                        operation_started,
                        answer_chars=len(answer),
                        generation_ms=generation_ms,
                        source_count=len(sources),
                        outcome="compact_grounded_retry",
                    )
            else:
                generation_ms = round((time.perf_counter() - generation_started) * 1000)
                log_progress(
                    logger,
                    "chat",
                    "answer_generation_completed",
                    operation_started,
                    answer_chars=len(answer),
                    generation_ms=generation_ms,
                    source_count=len(sources),
                )
            if (
                retrieval_route != "single_hop"
                and cache_lookup
                and verification.get("checked")
                and verification.get("all_current")
            ):
                try:
                    await answer_cache.store(
                        cache_lookup,
                        answer,
                        sources,
                        verification,
                    )
                except Exception:
                    logger.exception("Cannot store semantic answer cache entry")

    if is_new_conversation and greeting_answer is None:
        answer = f"Chào {preferred_name},\n\n{answer}"

    for timing_name, telemetry_name in {
        "generation_initial": "generation_initial_ms",
        "citation_normalize": "citation_normalize_ms",
        "citation_repair": "citation_repair_ms",
    }.items():
        timings[timing_name] = round(
            float(telemetry_details.get(telemetry_name, 0.0) or 0.0),
            1,
        )


    message_id = uuid.uuid4()
    persistence_started = time.perf_counter()
    log_progress(logger, "chat", "persistence_started", operation_started)
    if conversation_id is None:
        conversation = Conversation(
            user_id=authenticated_user_id,
            title=current_question[:100],
            retrieval_mode=settings.retriever_backend.upper(),
        )
        db.add(conversation)
        await db.flush()
        conversation_id = conversation.id
        lock_key = f"vlegal:conversation-messages:{conversation_id}"
        await db.execute(
            sql_text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )
    else:
        lock_key = f"vlegal:conversation-messages:{conversation_id}"
        await db.execute(
            sql_text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": lock_key},
        )
        # Authorization is re-evaluated after the network phase and while
        # the append lock is held, so deletion/ownership changes cannot be
        # bypassed by the earlier snapshot.
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == authenticated_user_id,
            )
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện")

    last_sequence = int(
        await db.scalar(
            select(func.max(ChatMessage.message_sequence)).where(
                ChatMessage.conversation_id == conversation_id
            )
        )
        or 0
    )
    assistant_sequence = last_sequence + 2
    feedback_to_link: ChatAnswerFeedback | None = None
    if regeneration_target_id is None:
        user_message = ChatMessage(
            conversation_id=conversation_id,
            message_sequence=last_sequence + 1,
            role="USER",
            content_ciphertext=encrypt_text(current_question, settings),
            content_hash=_hash_content(current_question),
            attachments=message_attachments,
            attachment_context_ciphertext=(
                encrypt_text(
                    serialize_attachment_context(attachment_payloads),
                    settings,
                )
                if attachment_payloads
                else None
            ),
        )
        db.add(user_message)
    else:
        assistant_sequence = last_sequence + 1
        target_message = await db.scalar(
            select(ChatMessage).where(
                ChatMessage.id == regeneration_target_id,
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.role == "ASSISTANT",
                ChatMessage.status == "COMPLETED",
            )
        )
        feedback = await db.scalar(
            select(ChatAnswerFeedback).where(
                ChatAnswerFeedback.id == regeneration_feedback_id,
                ChatAnswerFeedback.message_id == regeneration_target_id,
                ChatAnswerFeedback.rating == "BAD",
            )
        )
        if target_message is None or feedback is None:
            raise HTTPException(
                status_code=409,
                detail="Câu trả lời đã được thay đổi; vui lòng tải lại cuộc trò chuyện",
            )
        target_message.status = "SUPERSEDED"
        feedback_to_link = feedback
        await db.execute(
            delete(ConversationSummary).where(
                ConversationSummary.conversation_id == conversation_id
            )
        )
    assistant_message = ChatMessage(
        id=message_id,
        conversation_id=conversation_id,
        message_sequence=assistant_sequence,
        role="ASSISTANT",
        content_ciphertext=encrypt_text(answer, settings),
        content_hash=_hash_content(answer),
        sources=sources,
        verification=verification,
    )
    db.add(assistant_message)
    if feedback_to_link is not None:
        await db.flush()
        feedback_to_link.regenerated_message_id = message_id
    conversation.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(assistant_message)
    message_id = assistant_message.id
    if (
        greeting_answer is None
        and retrieval_route != "single_hop"
    ):
        try:
            await memory.refresh(conversation_id)
        except Exception:
            logger.exception(
                "Cannot refresh conversation summary for %s",
                conversation_id,
            )
    timings["persistence"] = round((time.perf_counter() - persistence_started) * 1000, 1)

    total_ms = round((time.perf_counter() - operation_started) * 1000, 1)
    timings["total"] = total_ms

    server_timing_parts = [f"{k};dur={v:.1f}" for k, v in timings.items()]
    if response is not None:
        response.headers["Server-Timing"] = ", ".join(server_timing_parts)

    outcome = (
        "greeting"
        if greeting_answer is not None
        else "catalog"
        if catalog_answer is not None
        else "cache_hit"
        if cache_hit
        else "fallback"
        if generation_fallback
        else "draft_valid"
    )

    if outcome == "fallback":
        logger.warning(
            "Legal chat failed request_id=%s outcome=fallback route=%s total_ms=%.1f "
            "failed_stage=%s exception_type=%s timeout_configured=%.1f elapsed_actual_ms=%.1f "
            "citation_repair_called=%s auth_ms=%.1f context_ms=%.1f routing_ms=%.1f cache_ms=%.1f rewrite_ms=%.1f "
            "structure_ms=%.1f retrieval_ms=%.1f evidence_gate_ms=%.1f freshness_ms=%.1f "
            "generation_initial_ms=%.1f citation_normalize_ms=%.1f citation_repair_ms=%.1f persistence_ms=%.1f",
            request_id,
            retrieval_route,
            total_ms,
            telemetry_details.get("failed_stage", "unknown"),
            telemetry_details.get("exception_type", "unknown"),
            telemetry_details.get("timeout_configured", 0.0),
            telemetry_details.get("elapsed_actual_ms", 0.0),
            telemetry_details.get("citation_repair_called", False),
            timings["auth"],
            timings["context"],
            timings["routing"],
            timings["cache"],
            timings["rewrite"],
            timings["structure"],
            timings["retrieval"],
            timings["evidence_gate"],
            timings["freshness"],
            timings["generation_initial"],
            timings["citation_normalize"],
            timings["citation_repair"],
            timings["persistence"],
        )
    else:
        logger.info(
            "Legal chat completed request_id=%s outcome=%s route=%s total_ms=%.1f "
            "auth_ms=%.1f context_ms=%.1f routing_ms=%.1f cache_ms=%.1f rewrite_ms=%.1f "
            "structure_ms=%.1f retrieval_ms=%.1f evidence_gate_ms=%.1f freshness_ms=%.1f generation_initial_ms=%.1f "
            "citation_normalize_ms=%.1f citation_repair_ms=%.1f persistence_ms=%.1f source_count=%d answer_chars=%d",
            request_id,
            outcome,
            retrieval_route,
            total_ms,
            timings["auth"],
            timings["context"],
            timings["routing"],
            timings["cache"],
            timings["rewrite"],
            timings["structure"],
            timings["retrieval"],
            timings["evidence_gate"],
            timings["freshness"],
            timings["generation_initial"],
            timings["citation_normalize"],
            timings["citation_repair"],
            timings["persistence"],
            len(sources),
            len(answer),
        )
    return ChatResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        replaces_message_id=regeneration_target_id,
        answer=answer,
        sources=sources,
        verification=verification,
        temporary=False,
        cache_hit=cache_hit,
        cache_similarity=cache_similarity,
        cache_mode=cache_mode,
    )


async def _save_artifact(
    db: AsyncSession,
    user_id: uuid.UUID,
    settings: Settings,
    *,
    kind: str,
    title: str,
    content: str,
    metadata: dict[str, Any],
) -> Artifact:
    active_user_id = await db.scalar(
        select(User.id).where(User.id == user_id, User.is_active.is_(True))
    )
    if active_user_id is None:
        raise HTTPException(
            status_code=401,
            detail="Tài khoản không còn hoạt động",
        )
    artifact = Artifact(
        user_id=active_user_id,
        kind=kind,
        title=title[:220],
        content_ciphertext=encrypt_text(content, settings),
        metadata_json=metadata,
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact


@router.post("/contracts/draft")
async def draft_contract(
    payload: DraftContractRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    retrieval: RetrievalService = Depends(retrieval_service),
    freshness: LegalFreshnessService = Depends(freshness_service),
    ai: GeminiService = Depends(ai_service),
) -> dict[str, Any]:
    operation_started = time.perf_counter()
    log_progress(logger, "contract_draft", "started", operation_started)
    user_id = user.id
    await db.rollback()
    template_definition = _resolve_labor_contract_template(payload)
    template = template_definition["name"]
    requirements = payload.prompt.strip()
    source_text = (payload.source_text or "").strip()
    # Backwards compatibility for the old one-field UI: a pasted contract is
    # treated as a source document instead of being sent to retrieval as a huge
    # multi-hop question.
    if not source_text and looks_like_contract(requirements):
        source_text = requirements
        requirements = "Rà soát, chuẩn hóa và hoàn thiện bản hợp đồng được cung cấp."
    _ensure_labor_contract_source(source_text)

    query = contract_retrieval_query(
        f"Căn cứ và điều kiện bắt buộc để soạn {template}",
        source_text or requirements,
    )
    sources, verification = await _legal_sources(
        query,
        retrieval,
        freshness,
    )
    log_progress(
        logger,
        "contract_draft",
        "sources_ready",
        operation_started,
        source_count=len(sources),
    )
    task = (
        "Hãy chỉnh lý và trả lại TOÀN BỘ hợp đồng hoàn chỉnh dựa trên bản hiện có. "
        "Giữ nội dung hợp lý, sửa điểm mâu thuẫn hoặc thiếu và dùng [ngoặc vuông] cho dữ liệu chưa có."
        if source_text
        else "Hãy soạn TOÀN BỘ hợp đồng hoàn chỉnh theo yêu cầu."
    )
    draft = await ai.complete(
        CONTRACT_SYSTEM_PROMPT,
        f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\nNGUỒN:\n{build_context(sources)}\n\n"
        f"{task}\n"
        f"{untrusted_data_block('CONTRACT_REQUEST', {'template': template, 'requirements': requirements})}\n"
        f"{untrusted_data_block('SOURCE_CONTRACT', source_text) if source_text else ''}\n"
        "PHẠM VI BẮT BUỘC: Chỉ soạn văn bản liên quan trực tiếp đến quan hệ lao động.\n"
        "ĐỊNH DẠNG BẮT BUỘC:\n"
        "- Chỉ trả về toàn bộ nội dung văn bản hoàn chỉnh; không có lời mở đầu, lời giải thích, "
        "checklist hoặc lời kết của trợ lý.\n"
        "- Dùng văn bản thuần, tuyệt đối không dùng Markdown, ký hiệu #, **, ``` hoặc bảng Markdown.\n"
        "- Không chèn mã nguồn [S1], [S2] vào nội dung hợp đồng; căn cứ được hiển thị riêng ngoài văn bản.\n"
        "- Bố cục theo văn bản Việt Nam: quốc hiệu, tiêu ngữ; tên và số hợp đồng; căn cứ; "
        "thông tin người sử dụng lao động và người lao động; các Điều; chữ ký.\n"
        "- Tùy loại văn bản, phải thể hiện đầy đủ công việc và địa điểm làm việc, thời hạn, "
        "thời giờ làm việc/nghỉ ngơi, tiền lương và phương thức trả lương, phụ cấp, bảo hiểm, "
        "an toàn lao động, quyền/nghĩa vụ, sửa đổi/chấm dứt, giải quyết tranh chấp, hiệu lực và số bản.\n"
        "- Dữ liệu chưa được cung cấp phải để dưới dạng [Thông tin cần điền], không tự bịa.\n"
        "- Khối ký cuối văn bản dùng hai cột văn bản thuần, ngăn bởi một ký tự TAB; ví dụ tiêu đề hai bên "
        "trên cùng một dòng và hướng dẫn ký trên dòng kế tiếp.",
        max_tokens=8192,
        temperature=0.12,
        thinking_budget=1024,
    )
    validate_citations(
        draft,
        [source["source_id"] for source in sources],
        require=False,
        require_claim_coverage=False,
    )
    draft = normalize_contract_plain_text(draft, template)
    checklist = [
        "Điền và đối chiếu thông tin người sử dụng lao động, người lao động và thẩm quyền ký.",
        "Kiểm tra công việc, địa điểm làm việc, loại và thời hạn hợp đồng.",
        "Chốt mức lương, hình thức trả lương, phụ cấp, thời giờ làm việc và thời giờ nghỉ ngơi.",
        "Đối chiếu bảo hiểm bắt buộc, an toàn lao động, quyền đơn phương chấm dứt và trách nhiệm bồi thường.",
        "Rà soát bản cuối và ký đủ số bản sau khi mọi chỗ [Thông tin cần điền] đã được hoàn thiện.",
    ]
    artifact = await _save_artifact(
        db, user_id, settings, kind="CONTRACT_DRAFT", title=template, content=draft,
        metadata={
            "sources": sources,
            "verification": verification,
            "checklist": checklist,
            "mode": "revise" if source_text else "new",
        },
    )
    log_progress(
        logger,
        "contract_draft",
        "completed",
        operation_started,
        source_count=len(sources),
        mode="revise" if source_text else "new",
    )
    return {
        "artifact_id": str(artifact.id), "title": template, "draft": draft, "checklist": checklist,
        "sources": sources, "verification": verification, "model": settings.gemini_model,
        "download_url": f"/api/contracts/draft/{artifact.id}/docx",
    }


@router.get("/contracts/draft/{artifact_id}/docx")
async def download_contract_draft_docx(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.user_id == user.id,
            Artifact.kind == "CONTRACT_DRAFT",
        )
    )
    if not artifact:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy bản hợp đồng lao động",
        )

    content = decrypt_text(artifact.content_ciphertext, settings)
    document_bytes = await run_in_threadpool(
        build_contract_docx,
        artifact.title,
        content,
    )
    filename = contract_download_filename(artifact.title)
    encoded_filename = quote(filename)
    return StreamingResponse(
        io.BytesIO(document_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"; '
                f"filename*=UTF-8''{encoded_filename}"
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/contracts/review")
async def review_contract(
    payload: ReviewContractRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    retrieval: RetrievalService = Depends(retrieval_service),
    freshness: LegalFreshnessService = Depends(freshness_service),
    ai: GeminiService = Depends(ai_service),
) -> dict[str, Any]:
    operation_started = time.perf_counter()
    log_progress(logger, "contract_review", "started", operation_started)
    user_id = user.id
    await db.rollback()
    query = contract_retrieval_query(
        "Rà soát điều khoản và rủi ro hợp đồng",
        payload.text,
    )
    sources, verification = await _legal_sources(
        query,
        retrieval,
        freshness,
    )
    log_progress(
        logger,
        "contract_review",
        "sources_ready",
        operation_started,
        source_count=len(sources),
    )
    result = await ai.complete_json(
        CONTRACT_SYSTEM_PROMPT,
        f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\n"
        f"NGUỒN:\n{build_context(sources)}\n\n"
        "Hãy review toàn bộ hợp đồng, không chỉ tóm tắt. Xác định loại hợp đồng, "
        "các điều khoản chính, điểm bất lợi theo góc nhìn của người dùng, điều khoản "
        "còn thiếu, mức độ rủi ro và câu chữ đề xuất sửa. Phân biệt rõ nhận xét về "
        "nội dung hợp đồng với kết luận dựa trên pháp luật.\n"
        f"{untrusted_data_block('USER_PERSPECTIVE', payload.user_role or 'Chưa xác định; đánh giá cân bằng cho cả hai bên')}\n"
        f"{untrusted_data_block('CONTRACT_TITLE', payload.title or '')}\n"
        f"{untrusted_data_block('CONTRACT_TEXT', payload.text)}",
        schema=REVIEW_SCHEMA,
        max_tokens=8192,
        thinking_budget=2048,
    )
    allowed_ids = [source["source_id"] for source in sources]
    validate_citations(result, allowed_ids, require=False)
    _validate_narrative_claims(result["summary"], allowed_ids)
    _validate_narrative_claims(result["recommendations"], allowed_ids)
    artifact = await _save_artifact(
        db, user_id, settings, kind="CONTRACT_REVIEW", title=payload.title or "Kết quả review hợp đồng",
        content=result["summary"], metadata={**result, "sources": sources, "verification": verification},
    )
    log_progress(
        logger,
        "contract_review",
        "completed",
        operation_started,
        risk_count=len(result["risks"]),
        clause_count=len(result["clause_reviews"]),
    )
    return {**result, "artifact_id": str(artifact.id), "sources": sources, "verification": verification, "model": settings.gemini_model}


@router.post("/contracts/compare")
async def compare_contracts(
    payload: CompareContractRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    retrieval: RetrievalService = Depends(retrieval_service),
    freshness: LegalFreshnessService = Depends(freshness_service),
    ai: GeminiService = Depends(ai_service),
) -> dict[str, Any]:
    operation_started = time.perf_counter()
    log_progress(logger, "contract_compare", "started", operation_started)
    user_id = user.id
    await db.rollback()
    diff_context = await run_in_threadpool(
        build_contract_diff,
        payload.original_text,
        payload.revised_text,
    )
    if not diff_context["changes"] and not diff_context["omitted_change_groups"]:
        verification = VerificationReport(
            checked=False,
            all_current=False,
            checked_at=datetime.now(UTC),
            note="Hai phiên bản giống nhau; không phát sinh thay đổi pháp lý cần kiểm tra.",
        ).model_dump(mode="json")
        result = {
            "summary": "Hai phiên bản hợp đồng không có khác biệt về nội dung.",
            "important_changes": [],
            "differences": [],
            "risks": [],
            "recommendation": "Không cần xử lý thay đổi. Hãy kiểm tra lại định dạng và phụ lục nếu có.",
            "similarity": 100,
            "change_counts": diff_context["counts"],
            "analysis_truncated": False,
        }
        artifact = await _save_artifact(
            db,
            user_id,
            settings,
            kind="CONTRACT_COMPARE",
            title="So sánh hợp đồng",
            content=result["summary"],
            metadata={**result, "sources": [], "verification": verification},
        )
        log_progress(
            logger,
            "contract_compare",
            "completed",
            operation_started,
            outcome="identical",
        )
        return {
            **result,
            "artifact_id": str(artifact.id),
            "sources": [],
            "verification": verification,
            "model": settings.gemini_model,
        }

    query = contract_retrieval_query(
        "Đánh giá tác động pháp lý của thay đổi hợp đồng",
        payload.original_text,
        payload.revised_text,
    )
    sources, verification = await _legal_sources(
        query,
        retrieval,
        freshness,
    )
    log_progress(
        logger,
        "contract_compare",
        "sources_ready",
        operation_started,
        source_count=len(sources),
        structural_change_count=len(diff_context["changes"]),
    )
    result = await ai.complete_json(
        CONTRACT_SYSTEM_PROMPT,
        f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\nNGUỒN:\n{build_context(sources)}\n\n"
        "Đối chiếu các nhóm thay đổi đã được máy xác định. Liệt kê nội dung được thêm, "
        "xóa hoặc sửa; ghép với điều khoản tương ứng; ưu tiên thay đổi về tiền, thời hạn, "
        "trách nhiệm, phạt, bồi thường và chấm dứt. Tóm tắt các thay đổi quan trọng và "
        "tác động đối với người ký. Không tự tạo khác biệt ngoài dữ liệu STRUCTURAL_DIFF.\n"
        f"{untrusted_data_block('DOCUMENT_TITLES', {'original': payload.original_title, 'revised': payload.revised_title})}\n"
        f"{untrusted_data_block('STRUCTURAL_DIFF', diff_context)}",
        schema=COMPARE_SCHEMA,
        max_tokens=8192,
        thinking_budget=2048,
    )
    allowed_ids = [source["source_id"] for source in sources]
    validate_citations(result, allowed_ids, require=False)
    _validate_narrative_claims(result["summary"], allowed_ids)
    _validate_narrative_claims(result["recommendation"], allowed_ids)
    result["similarity"] = diff_context["similarity"]
    result["change_counts"] = diff_context["counts"]
    result["analysis_truncated"] = diff_context["truncated_for_analysis"]
    artifact = await _save_artifact(
        db, user_id, settings, kind="CONTRACT_COMPARE", title="So sánh hợp đồng",
        content=result["summary"], metadata={**result, "sources": sources, "verification": verification},
    )
    log_progress(
        logger,
        "contract_compare",
        "completed",
        operation_started,
        difference_count=len(result["differences"]),
        analysis_truncated=result["analysis_truncated"],
    )
    return {**result, "artifact_id": str(artifact.id), "sources": sources, "verification": verification, "model": settings.gemini_model}


@router.post("/artifacts", response_model=ArtifactOut, status_code=201)
async def create_artifact(
    payload: ArtifactCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> ArtifactOut:
    artifact = Artifact(
        user_id=user.id, kind=payload.kind, title=payload.title,
        content_ciphertext=encrypt_text(payload.content, settings), metadata_json=payload.metadata, status=payload.status,
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return _artifact_out(artifact, settings)


@router.get("/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(
    kind: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> list[ArtifactOut]:
    statement = select(Artifact).where(Artifact.user_id == user.id).order_by(Artifact.updated_at.desc()).limit(limit)
    if kind:
        statement = statement.where(Artifact.kind == kind)
    return [_artifact_out(row, settings) for row in (await db.scalars(statement)).all()]


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
async def get_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> ArtifactOut:
    artifact = await db.scalar(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user.id))
    if not artifact:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    return _artifact_out(artifact, settings)


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactOut)
async def update_artifact(
    artifact_id: uuid.UUID,
    payload: ArtifactUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> ArtifactOut:
    artifact = await db.scalar(select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user.id))
    if not artifact:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    values = payload.model_dump(exclude_unset=True)
    if "content" in values:
        artifact.content_ciphertext = encrypt_text(values.pop("content"), settings)
    if "metadata" in values:
        artifact.metadata_json = values.pop("metadata")
    for field, value in values.items():
        setattr(artifact, field, value)
    await db.commit()
    await db.refresh(artifact)
    return _artifact_out(artifact, settings)


@router.delete("/artifacts/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> Response:
    result = await db.execute(delete(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user.id))
    if not result.rowcount:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu")
    await db.commit()
    return Response(status_code=204)


def _article_dict(article: Article) -> dict[str, Any]:
    return {
        "id": str(article.id), "slug": article.slug, "title": article.title, "excerpt": article.excerpt,
        "content": article.content, "category": article.category, "status": article.status,
        "source_url": article.source_url, "web_sources": article.web_sources, "views": article.view_count,
        "published_at": article.published_at, "created_at": article.created_at, "updated_at": article.updated_at,
    }


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return f"{value[:180] or 'bai-viet'}-{uuid.uuid4().hex[:6]}"


@router.get("/articles")
async def list_articles(
    q: str = "",
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100_000),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    filters: list[Any] = []
    if not user or user.role not in {"ADMIN", "REVIEWER"}:
        filters.append(Article.status == "PUBLISHED")
    if q.strip():
        like = f"%{q.strip()}%"
        filters.append(
            (Article.title.ilike(like))
            | (Article.excerpt.ilike(like))
            | (Article.content.ilike(like))
        )
    total = int(
        await db.scalar(
            select(func.count()).select_from(Article).where(*filters)
        )
        or 0
    )
    statement = (
        select(Article)
        .where(*filters)
        .order_by(
            Article.published_at.desc().nullslast(),
            Article.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    items = [_article_dict(row) for row in (await db.scalars(statement)).all()]
    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(items) < total,
    }


@router.get("/articles/{slug}")
async def get_article(slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    article = await db.scalar(select(Article).where(Article.slug == slug, Article.status == "PUBLISHED"))
    if not article:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài viết")
    article.view_count += 1
    await db.commit()
    await db.refresh(article)
    return _article_dict(article)


@router.post("/articles/web-search")
async def web_search_articles(
    payload: ArticleSearchRequest,
    research: ArticleResearchService = Depends(article_research_service),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, Any]:
    user_id = user.id
    await db.rollback()
    result = await research.search(payload.query)
    if payload.save:
        active_user_id = await db.scalar(
            select(User.id).where(User.id == user_id, User.is_active.is_(True))
        )
        if active_user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Tài khoản không còn hoạt động",
            )
        article = Article(
            author_id=active_user_id,
            slug=_slugify(payload.query),
            title=f"Nghiên cứu: {payload.query}",
            excerpt=result["summary"][:500],
            content=result["summary"],
            category="Nghiên cứu web",
            status="DRAFT",
            web_sources=result["sources"],
        )
        db.add(article)
        await db.commit()
        await db.refresh(article)
        result["article"] = _article_dict(article)
    return result


@router.post("/articles", status_code=201)
async def create_article(
    payload: ArticleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("ADMIN", "REVIEWER")),
) -> dict[str, Any]:
    article = Article(
        author_id=user.id, slug=_slugify(payload.title), **payload.model_dump(),
        published_at=datetime.now(UTC) if payload.status == "PUBLISHED" else None,
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return _article_dict(article)


@router.patch("/articles/{article_id}")
async def update_article(
    article_id: uuid.UUID,
    payload: ArticleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("ADMIN", "REVIEWER")),
) -> dict[str, Any]:
    article = await db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài viết")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(article, field, value)
    if payload.status == "PUBLISHED" and not article.published_at:
        article.published_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(article)
    return _article_dict(article)


@router.delete("/articles/{article_id}", status_code=204)
async def delete_article(
    article_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles("ADMIN")),
) -> Response:
    article = await db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài viết")
    await db.delete(article)
    await db.commit()
    return Response(status_code=204)


@router.post("/signatures/prepare", status_code=201)
async def prepare_signature(
    payload: PrepareSignatureRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    digest = hashlib.sha256(payload.document_text.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)
    signers = [{"name": name.strip(), "status": "PENDING"} for name in payload.signers if name.strip()]
    audit = [{"time": now.isoformat(), "event": "Tạo gói ký", "actor": user.display_name}]
    packet = SignaturePacket(
        user_id=user.id, title=payload.title, document_ciphertext=encrypt_text(payload.document_text, settings),
        document_hash=digest, signers=signers, audit_log=audit,
    )
    db.add(packet)
    await db.commit()
    await db.refresh(packet)
    return {
        "signature_id": str(packet.id), "title": packet.title, "status": packet.status.lower(),
        "document_hash": digest, "signers": [item["name"] for item in signers], "audit_log": audit,
        "next_steps": ["Kiểm tra bản cuối", "Xác thực danh tính người ký", "Gửi qua nhà cung cấp chữ ký số được cấp phép"],
    }


@router.post("/feedback", status_code=201)
async def feedback(
    payload: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User | None = Depends(optional_user),
) -> dict[str, bool]:
    db.add(UserFeedback(
        user_id=user.id if user else None,
        message_ciphertext=encrypt_text(payload.message, settings),
        page=payload.page,
    ))
    await db.commit()
    return {"ok": True}
