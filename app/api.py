from __future__ import annotations

import hashlib
import logging
import re
import time
import unicodedata
import uuid
from binascii import Error as BinasciiError
from datetime import UTC, datetime
from typing import Any

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
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user, optional_user, require_roles
from app.auth import router as auth_router
from app.core.config import Settings, get_settings
from app.core.observability import log_progress
from app.core.security import decrypt_text, encrypt_text
from app.db import get_db
from app.models import (
    Article,
    Artifact,
    ChatMessage,
    Conversation,
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
    ChatRequest,
    ChatResponse,
    CompareContractRequest,
    ConversationCreate,
    ConversationDetailOut,
    ConversationOut,
    ConversationUpdate,
    DraftContractRequest,
    FeedbackRequest,
    MessageOut,
    PrepareSignatureRequest,
    ReviewContractRequest,
    SourceOut,
    VerificationReport,
)
from app.services.ai import (
    CONTRACT_SYSTEM_PROMPT,
    LEGAL_SYSTEM_PROMPT,
    GeminiError,
    GeminiService,
    untrusted_data_block,
    validate_citations,
)
from app.services.articles import ArticleResearchService
from app.services.chat_effort import ChatEffort, chat_effort_profile
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
from app.services.conversation_memory import ConversationMemoryService
from app.services.embeddings import (
    VertexAIEmbeddingService,
    embedding_config_from_settings,
    get_embedding_service,
)
from app.services.freshness import (
    CURRENT_STATUSES,
    LAW_CODE_RE,
    FreshnessUnavailable,
    LegalFreshnessService,
)
from app.services.greetings import greeting_response
from app.services.query_rewrite import rewrite_query_if_needed
from app.services.retrieval import (
    RetrievalService,
    build_answer_plan,
    build_context,
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


CONTRACT_TEMPLATES = [
    {"id": "employment", "name": "Hợp đồng lao động", "category": "Lao động"},
    {"id": "probation", "name": "Hợp đồng thử việc", "category": "Lao động"},
    {"id": "nda", "name": "Thỏa thuận bảo mật", "category": "Doanh nghiệp"},
    {"id": "service", "name": "Hợp đồng dịch vụ", "category": "Dịch vụ"},
    {"id": "sale", "name": "Hợp đồng mua bán hàng hóa", "category": "Thương mại"},
    {"id": "lease", "name": "Hợp đồng thuê", "category": "Dân sự"},
    {"id": "loan", "name": "Hợp đồng vay", "category": "Dân sự"},
    {"id": "agency", "name": "Hợp đồng đại lý", "category": "Thương mại"},
]


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


def _hash_content(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _artifact_out(artifact: Artifact, settings: Settings) -> ArtifactOut:
    return ArtifactOut(
        id=artifact.id,
        kind=artifact.kind,
        title=artifact.title,
        content=decrypt_text(artifact.content_ciphertext, settings),
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


def _message_content_out(message: ChatMessage, settings: Settings) -> str:
    try:
        return decrypt_text(message.content_ciphertext, settings)
    except (BinasciiError, InvalidTag, UnicodeDecodeError, ValueError):
        logger.exception("Cannot decrypt stored chat message message_id=%s", message.id)
        return "Không thể khôi phục nội dung tin nhắn này."


def _message_out(message: ChatMessage, settings: Settings) -> MessageOut:
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
        created_at=message.created_at,
    )


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


async def _legal_sources(
    query: str,
    retrieval: RetrievalService,
    freshness: LegalFreshnessService,
    *,
    allow_empty: bool = False,
    effort: ChatEffort = "medium",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    operation_started = time.perf_counter()
    log_progress(
        logger,
        "legal_sources",
        "started",
        operation_started,
        allow_empty=allow_empty,
        effort=effort,
    )

    async def retrieve_sources(retrieval_query: str) -> list[dict[str, Any]]:
        effort_retriever = getattr(retrieval, "retrieve_for_effort", None)
        if callable(effort_retriever):
            return await effort_retriever(retrieval_query, effort)
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

    configured_limit = getattr(
        getattr(freshness, "settings", None),
        "max_laws_verified_per_request",
        16,
    )
    try:
        source_limit = max(1, int(configured_limit))
    except (TypeError, ValueError):
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

    retrieval_query = query
    followed_replacements: set[str] = set()
    verification: Any = None
    require_freshness = bool(
        getattr(
            getattr(freshness, "settings", None),
            "require_freshness_check",
            True,
        )
    )
    for attempt in range(1, 4):
        freshness_started = time.perf_counter()
        log_progress(
            logger,
            "legal_sources",
            "freshness_started",
            operation_started,
            attempt=attempt,
            source_count=len(sources),
        )
        try:
            verification, updated = await freshness.verify_sources(sources)
        except FreshnessUnavailable as exc:
            logger.warning(
                "Freshness verification unavailable error_type=%s",
                type(exc).__name__,
            )
            if allow_empty:
                return unavailable_result()
            raise HTTPException(
                status_code=503,
                detail="Không thể kiểm tra hiệu lực văn bản tại thời điểm này.",
            ) from exc
        except Exception as exc:
            logger.warning(
                "Freshness verification failed error_type=%s",
                type(exc).__name__,
            )
            if allow_empty:
                return unavailable_result()
            raise HTTPException(
                status_code=503,
                detail="Không thể kiểm tra hiệu lực văn bản tại thời điểm này.",
            ) from exc

        raw_items = getattr(verification, "items", [])
        verification_items = (
            list(raw_items or [])
            if not callable(raw_items)
            else []
        )
        log_progress(
            logger,
            "legal_sources",
            "freshness_completed",
            operation_started,
            attempt=attempt,
            item_count=len(verification_items),
            phase_ms=round((time.perf_counter() - freshness_started) * 1000),
            updated=updated,
        )
        verified_statuses = {
            str(getattr(item, "code", "") or "").strip().upper():
            str(getattr(item, "status", "") or "").strip().upper()
            for item in verification_items
        }
        current_sources = [
            source
            for source in sources
            if verified_statuses.get(source_law_code(source)) in CURRENT_STATUSES
        ]
        replacement_codes = []
        for item in verification_items:
            replacement_code = str(
                getattr(item, "replacement_code", "") or ""
            ).strip().upper()
            item_status = str(
                getattr(item, "status", "") or ""
            ).strip().upper()
            if (
                item_status not in CURRENT_STATUSES
                and replacement_code
                and replacement_code not in followed_replacements
            ):
                replacement_codes.append(replacement_code)

        if updated or replacement_codes:
            followed_replacements.update(replacement_codes)
            retrieval_query = " ".join([query, *sorted(followed_replacements)])
            replacement_retrieval_started = time.perf_counter()
            log_progress(
                logger,
                "legal_sources",
                "replacement_retrieval_started",
                operation_started,
                replacement_count=len(followed_replacements),
            )
            sources = usable_sources(await retrieve_sources(retrieval_query))
            log_progress(
                logger,
                "legal_sources",
                "replacement_retrieval_completed",
                operation_started,
                phase_ms=round(
                    (time.perf_counter() - replacement_retrieval_started) * 1000
                ),
                source_count=len(sources),
            )
            if not sources:
                if allow_empty:
                    return unavailable_result()
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Chỉ mục đã được cập nhật nhưng chưa có văn bản thay thế "
                        "phù hợp để trả lời an toàn."
                    ),
                )
            continue

        if verification_items:
            if not current_sources:
                if allow_empty:
                    return unavailable_result()
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Các văn bản truy hồi không được xác nhận là còn hiệu lực; "
                        "hệ thống không thể dùng chúng để kết luận."
                    ),
                )
            sources = current_sources
        elif require_freshness:
            if allow_empty:
                return unavailable_result()
            raise HTTPException(
                status_code=503,
                detail="Không nhận được bằng chứng kiểm tra hiệu lực văn bản.",
            )
        break
    else:
        if allow_empty:
            return unavailable_result()
        raise HTTPException(
            status_code=409,
            detail="Chuỗi văn bản thay thế vượt quá giới hạn xử lý an toàn.",
        )

    final_raw_items = getattr(verification, "items", [])
    final_items = (
        list(final_raw_items or [])
        if not callable(final_raw_items)
        else []
    )
    verified_statuses = {
        item.code.strip().upper(): item.status.strip().upper()
        for item in final_items
    }
    verification_by_code = {
        item.code.strip().upper(): item
        for item in final_items
    }
    verified_sources: list[dict[str, Any]] = []
    for source in sources:
        code = source_law_code(source)
        item = verification_by_code.get(code)
        if item is None or verified_statuses.get(code) not in CURRENT_STATUSES:
            continue
        enriched = dict(source)
        enriched["law_status"] = item.status
        enriched["source_url"] = (
            getattr(item, "source_url", None) or enriched.get("source_url")
        )
        checked_at = getattr(
            item,
            "checked_at",
            None,
        )
        enriched["law_checked_at"] = (
            checked_at.isoformat()
            if isinstance(checked_at, datetime)
            else checked_at
        )
        verified_sources.append(enriched)
    if verified_sources:
        sources = verified_sources
    for index, source in enumerate(sources, start=1):
        source["source_id"] = f"S{index}"
    verification_payload = (
        verification.model_dump(mode="json")
        if hasattr(verification, "model_dump")
        else {
            "checked": False,
            "all_current": False,
            "items": [],
        }
    )
    log_progress(
        logger,
        "legal_sources",
        "completed",
        operation_started,
        outcome="verified",
        source_count=len(sources),
        verified_law_count=len(final_items),
    )
    return sources, verification_payload


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
        raise GeminiError(
            "Câu trả lời nhắc đến số hiệu văn bản không có trong nguồn: "
            + ", ".join(sorted(unknown_codes))
        )

    allowed_titles: set[str] = set()
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
) -> str:
    operation_started = time.perf_counter()
    log_progress(
        logger,
        "answer_generation",
        "draft_started",
        operation_started,
        source_count=len(allowed_ids),
    )
    answer = await ai.complete(
        system,
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        thinking_budget=thinking_budget,
    )
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
        repair_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["statements"],
            "properties": {
                "statements": {
                    "type": "array",
                    "minItems": 1,
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
        structured = await ai.complete_json(
            system,
            repair_prompt,
            schema=repair_schema,
            max_tokens=max_tokens,
            temperature=0,
            thinking_budget=thinking_budget,
        )
        log_progress(
            logger,
            "answer_generation",
            "citation_repair_response_received",
            operation_started,
        )
        validate_citations(structured, allowed_ids)
        repaired_units: list[str] = []
        for statement in structured["statements"]:
            citations = list(dict.fromkeys(
                str(item).strip().upper()
                for item in statement["citations"]
            ))
            suffix = " ".join(f"[{item}]" for item in citations)
            text = re.sub(
                r"(?:\s*,?\s*\[(?:S\d+)\])+",
                "",
                str(statement["text"]),
                flags=re.IGNORECASE,
            ).strip()
            text = re.sub(r"\s+([,.!?;:])", r"\1", text)
            for unit in re.split(r"(?<=[.!?;])\s+|\n+", text):
                unit = unit.strip()
                if unit:
                    terminal = unit[-1] if unit[-1] in ".!?;" else ""
                    body = unit[:-1].rstrip() if terminal else unit
                    prefix = (
                        ""
                        if sources is not None and not repaired_units
                        else "- "
                    )
                    repaired_units.append(
                        f"{prefix}{body} {suffix}{terminal}"
                    )
        repaired = "\n".join(repaired_units)
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
            if draft_safety_valid:
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
            "Citation validation failed closed error_type=%s",
            type(exc).__name__,
        )
        raise GeminiError(
            "Không thể xác minh căn cứ của câu trả lời."
        ) from exc


async def _load_postgres_chat_history(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    settings: Settings,
    *,
    limit: int = 12,
) -> list[tuple[str, str]]:
    """Load persisted history from PostgreSQL in chronological order."""
    stored_messages = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.message_sequence.desc())
            .limit(limit)
        )
    ).all()
    return [
        (message.role, decrypt_text(message.content_ciphertext, settings))
        for message in reversed(stored_messages)
    ]


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
        .outerjoin(ChatMessage)
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
    messages = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.message_sequence)
        )
    ).all()
    return ConversationDetailOut(
        conversation=_conversation_out(conversation, len(messages)),
        messages=[_message_out(row, settings) for row in messages],
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
) -> ChatResponse:
    # A rollback expires ORM instances even when the session factory uses
    # expire_on_commit=False. Snapshot every user field needed after the
    # read transaction is released so later access cannot trigger implicit
    # async database IO (and therefore MissingGreenlet).
    authenticated_user_id = user.id
    preferred_name = user.preferred_name
    if not preferred_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vui lòng chọn tên gọi trước khi bắt đầu trò chuyện",
        )

    operation_started = time.perf_counter()
    effort_profile = chat_effort_profile(payload.effort)
    conversation: Conversation | None = None
    conversation_id: uuid.UUID | None = None
    is_new_conversation = payload.conversation_id is None
    log_progress(
        logger,
        "chat",
        "started",
        operation_started,
        authenticated=True,
        effort=effort_profile.name,
        has_conversation_id=bool(payload.conversation_id),
        history_turn_count=0,
    )
    cache_effort = (
        "medium"
        if effort_profile.name == "instant"
        else effort_profile.name
    )
    cache_scope = f"user:{authenticated_user_id}:effort:{cache_effort}"
    summary_context = ""
    history_turns: list[tuple[str, str]] = []
    greeting_answer = greeting_response(payload.message, preferred_name)
    if payload.conversation_id:
        conversation = await _owned_conversation(db, payload.conversation_id, user)
        conversation_id = conversation.id
        if greeting_answer is None:
            summary_context = await memory.get_summary(db, conversation_id)
            history_turns = await _load_postgres_chat_history(
                db,
                conversation_id,
                settings,
            )
    # Authentication and history reads must not retain a PostgreSQL
    # transaction while cache/search/Gemini network calls are in flight.
    await db.rollback()
    conversation = None

    log_progress(
        logger,
        "chat",
        "context_ready",
        operation_started,
        history_turn_count=len(history_turns),
        summary_available=bool(summary_context),
    )
    if greeting_answer is not None:
        retrieval_query = payload.message
        answer_plan: dict[str, Any] = {}
        query_was_rewritten = False
        log_progress(
            logger,
            "chat",
            "greeting_completed",
            operation_started,
            outcome="deterministic_response",
        )
    else:
        rewrite_started = time.perf_counter()
        log_progress(logger, "chat", "query_rewrite_started", operation_started)
        if effort_profile.skip_query_rewrite:
            retrieval_query = payload.message
            query_was_rewritten = False
            rewrite_attempted = False
        else:
            query_rewrite = await rewrite_query_if_needed(
                ai,
                payload.message,
                history=history_turns,
                settings=settings,
            )
            retrieval_query = query_rewrite.retrieval_query
            query_was_rewritten = query_rewrite.rewritten
            rewrite_attempted = query_rewrite.attempted
        answer_plan = build_answer_plan(retrieval_query)
        log_progress(
            logger,
            "chat",
            "query_rewrite_completed",
            operation_started,
            attempted=rewrite_attempted,
            effort=effort_profile.name,
            phase_ms=round((time.perf_counter() - rewrite_started) * 1000),
            rewritten=query_was_rewritten,
            skipped_for_effort=effort_profile.skip_query_rewrite,
        )

    cache_lookup: CacheLookup | None = None
    cache_hit = False
    cache_similarity: float | None = None
    cache_mode = "miss"
    cached_draft = ""
    answer = greeting_answer or ""
    sources: list[dict[str, Any]] = []
    verification: dict[str, Any] = (
        VerificationReport().model_dump(mode="json")
        if greeting_answer is not None
        else {}
    )
    answer_ready = greeting_answer is not None
    cache_eligible = (
        not answer_ready
        and answer_cache.eligible(
            payload.message,
            has_conversation_context=bool(history_turns or summary_context),
        )
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
            if effort_profile.name == "instant" and callable(exact_lookup):
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
                effort=effort_profile.name,
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
                effort=effort_profile.name,
            )
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
            try:
                answer = await _complete_with_citation_repair(
                    ai,
                    LEGAL_SYSTEM_PROMPT,
                    "BỘ NHỚ TÓM TẮT:\n"
                    f"{_summary_prompt(summary_context)}\n\n"
                    f"LỊCH SỬ HỘI THOẠI GẦN ĐÂY:\n{_chat_history_prompt(history_turns)}\n\n"
                    "KẾ HOẠCH PHỦ CÂU HỎI:\n"
                    f"{untrusted_data_block('ANSWER_PLAN', answer_plan)}\n\n"
                    f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\n"
                    f"NGUỒN:\n{build_context(sources)}\n\n"
                    f"CÂU HỎI HIỆN TẠI:\n{untrusted_data_block('CURRENT_QUESTION', payload.message)}"
                    "\n\nCÁCH HIỂU ĐÃ CHUẨN HÓA:\n"
                    f"{untrusted_data_block('REWRITTEN_QUERY', retrieval_query) if query_was_rewritten else '(Không cần chuẩn hóa)'}"
                    f"\n\nBẢN NHÁP CACHE THAM KHẢO:\n"
                    f"{untrusted_data_block('CACHE_DRAFT', cached_draft) if cached_draft else '(Không có)'}\n"
                    "Nếu có bản nháp, phải điều chỉnh theo đúng câu hỏi hiện tại; "
                    "không được sao chép các kết luận không còn phù hợp.",
                    allowed_ids=[source["source_id"] for source in sources],
                    sources=sources,
                    answer_plan=answer_plan,
                    max_tokens=effort_profile.max_output_tokens,
                    thinking_budget=effort_profile.thinking_budget,
                )
            except GeminiError as exc:
                logger.warning(
                    "Chat generation unavailable error_type=%s",
                    type(exc).__name__,
                )
                answer = AI_TEMPORARILY_UNAVAILABLE_MESSAGE
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
                    outcome="ai_unavailable",
                )
            else:
                log_progress(
                    logger,
                    "chat",
                    "answer_generation_completed",
                    operation_started,
                    answer_chars=len(answer),
                    source_count=len(sources),
                )
            if (
                effort_profile.name != "instant"
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

    message_id = uuid.uuid4()
    persistence_started = time.perf_counter()
    log_progress(logger, "chat", "persistence_started", operation_started)
    if conversation_id is None:
        conversation = Conversation(
            user_id=authenticated_user_id,
            title=payload.message[:100],
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
    user_message = ChatMessage(
        conversation_id=conversation_id,
        message_sequence=last_sequence + 1,
        role="USER",
        content_ciphertext=encrypt_text(payload.message, settings),
        content_hash=_hash_content(payload.message),
    )
    db.add(user_message)
    assistant_message = ChatMessage(
        conversation_id=conversation_id,
        message_sequence=last_sequence + 2,
        role="ASSISTANT",
        content_ciphertext=encrypt_text(answer, settings),
        content_hash=_hash_content(answer),
        sources=sources,
        verification=verification,
    )
    db.add(assistant_message)
    conversation.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(assistant_message)
    message_id = assistant_message.id
    if (
        greeting_answer is None
        and effort_profile.name != "instant"
    ):
        try:
            await memory.refresh(conversation_id)
        except Exception:
            # The full encrypted transcript is already durable. A later turn
            # retries every message after last_message_sequence automatically.
            logger.exception(
                "Cannot refresh conversation summary for %s",
                conversation_id,
            )
    log_progress(
        logger,
        "chat",
        "persistence_completed",
        operation_started,
        phase_ms=round((time.perf_counter() - persistence_started) * 1000),
    )
    log_progress(
        logger,
        "chat",
        "completed",
        operation_started,
        cache_mode=cache_mode,
        effort=effort_profile.name,
        source_count=len(sources),
        greeting=greeting_answer is not None,
        temporary=False,
    )
    return ChatResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        answer=answer,
        sources=sources,
        verification=verification,
        temporary=False,
        cache_hit=cache_hit,
        cache_similarity=cache_similarity,
        cache_mode=cache_mode,
        effort=effort_profile.name,
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
    template = payload.template_name or next(
        (item["name"] for item in CONTRACT_TEMPLATES if item["id"] == payload.template_id), "Hợp đồng"
    )
    requirements = payload.prompt.strip()
    source_text = (payload.source_text or "").strip()
    # Backwards compatibility for the old one-field UI: a pasted contract is
    # treated as a source document instead of being sent to retrieval as a huge
    # multi-hop question.
    if not source_text and looks_like_contract(requirements):
        source_text = requirements
        requirements = "Rà soát, chuẩn hóa và hoàn thiện bản hợp đồng được cung cấp."

    query = contract_retrieval_query(
        f"Căn cứ và điều kiện bắt buộc để soạn {template}",
        source_text or requirements,
    )
    sources, verification = await _legal_sources(
        query,
        retrieval,
        freshness,
        effort="instant",
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
        "Bao gồm căn cứ và lưu ý pháp lý, định nghĩa, quyền/nghĩa vụ, thanh toán, "
        "vi phạm, bồi thường, chấm dứt, tranh chấp và phần ký. Chỉ gắn [Sx] vào "
        "nhận định pháp lý; điều khoản thương mại do người dùng cung cấp không cần trích dẫn.",
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
    checklist = [
        "Điền và đối chiếu thông tin pháp lý của các bên.",
        "Kiểm tra thẩm quyền ký và tài liệu ủy quyền.",
        "Chốt các mốc bàn giao, nghiệm thu, thanh toán và thuế.",
        "Rà soát phạt vi phạm, bồi thường, chấm dứt và giải quyết tranh chấp.",
        "Luật sư kiểm tra bản cuối trước khi ký nếu giao dịch có giá trị hoặc rủi ro cao.",
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
    }


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
        effort="instant",
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
        effort="instant",
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
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict[str, Any]:
    statement = select(Article).order_by(Article.published_at.desc().nullslast(), Article.created_at.desc()).limit(limit)
    if not user or user.role not in {"ADMIN", "REVIEWER"}:
        statement = statement.where(Article.status == "PUBLISHED")
    if q.strip():
        like = f"%{q.strip()}%"
        statement = statement.where((Article.title.ilike(like)) | (Article.excerpt.ilike(like)))
    return {"items": [_article_dict(row) for row in (await db.scalars(statement)).all()]}


@router.get("/articles/{slug}")
async def get_article(slug: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    article = await db.scalar(select(Article).where(Article.slug == slug, Article.status == "PUBLISHED"))
    if not article:
        raise HTTPException(status_code=404, detail="Không tìm thấy bài viết")
    article.view_count += 1
    await db.commit()
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
