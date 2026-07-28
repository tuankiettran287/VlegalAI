from __future__ import annotations

import difflib
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
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from sqlalchemy import delete, func, select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import current_user, optional_user, require_roles, router as auth_router
from app.core.config import Settings, get_settings
from app.core.security import create_guest_token, decode_guest_token, decrypt_text, encrypt_text
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
from app.services.guest_limit import GuestRateLimitExceeded, GuestRateLimitUnavailable, GuestRateLimiter
from app.services.retrieval import (
    RetrievalService,
    append_detailed_citations,
    build_answer_plan,
    build_context,
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

_UNCLOSED_CITATION_RE = re.compile(
    r"(?<!\w)\[\s*([A-Z])\s*(\d+)\s*(?!\])(?=[.,;:!?)]|$)",
    re.IGNORECASE,
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


REVIEW_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "risks", "recommendations"],
    "properties": {
        "summary": {
            "type": "string",
            "description": "Tóm tắt có [S1], [S2] ngay sau từng nhận định pháp lý.",
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
                        "minItems": 1,
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
    "required": ["summary", "differences", "risks", "recommendation"],
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
                "required": ["type", "before", "after", "legal_impact", "citations"],
                "properties": {
                    "type": {"type": "string"},
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                    "legal_impact": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "string",
                            "pattern": r"^(?:S\d+|\[S\d+\])$",
                        },
                    },
                },
            },
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


def guest_rate_limiter(request: Request) -> GuestRateLimiter:
    return request.app.state.guest_limiter


def conversation_memory_service(request: Request) -> ConversationMemoryService:
    return request.app.state.conversation_memory


def semantic_answer_cache_service(request: Request) -> SemanticAnswerCacheService:
    return request.app.state.semantic_answer_cache


def _hash_content(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _guest_rate_subject(request: Request, response: Response, settings: Settings) -> str:
    token = request.cookies.get("vlegal_guest")
    guest_id = ""
    if token:
        try:
            guest_id = str(uuid.UUID(str(decode_guest_token(token, settings)["sub"])))
        except Exception:
            guest_id = ""
    if not guest_id:
        guest_id = str(uuid.uuid4())
        response.set_cookie(
            "vlegal_guest",
            create_guest_token(guest_id, settings),
            max_age=24 * 60 * 60,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/api",
        )
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[-1].strip() if forwarded else (request.client.host if request.client else "unknown")
    return _hash_content(f"{guest_id}:{client_ip}")


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
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
        explicit_code = str(source.get("law_code") or "").strip().upper()
        if explicit_code:
            return explicit_code
        label = f"{source.get('citation', '')} {source.get('title', '')}"
        match = LAW_CODE_RE.search(label.upper())
        if match:
            return match.group(0).upper()
        return ""

    try:
        sources = usable_sources(await retrieval.retrieve(query))
    except Exception as exc:
        logger.warning("Retrieval failed: %s", exc)
        sources = []
    if not sources:
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
    if not require_freshness:
        for index, source in enumerate(sources, start=1):
            source["source_id"] = f"S{index}"
        return sources, {
            "checked": False,
            "all_current": False,
            "items": [],
            "reason": "freshness_check_disabled",
        }

    for _ in range(3):
        try:
            verification, updated = await freshness.verify_sources(sources)
        except FreshnessUnavailable as exc:
            logger.warning(
                "Freshness verification unavailable error_type=%s",
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="Không thể kiểm tra hiệu lực văn bản tại thời điểm này.",
            ) from exc
        except Exception as exc:
            logger.warning(
                "Freshness verification failed error_type=%s",
                type(exc).__name__,
            )
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
            sources = usable_sources(await retrieval.retrieve(retrieval_query))
            if not sources:
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
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Các văn bản truy hồi không được xác nhận là còn hiệu lực; "
                        "hệ thống không thể dùng chúng để kết luận."
                    ),
                )
            sources = current_sources
        elif require_freshness:
            raise HTTPException(
                status_code=503,
                detail="Không nhận được bằng chứng kiểm tra hiệu lực văn bản.",
            )
        break
    else:
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
    return re.sub(r"\s+", " ", without_marks).strip().lower()


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
        if any(code.lower() in normalized_tail for code in allowed_codes):
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


def _grounded_source_fallback(
    sources: list[dict[str, Any]],
    *,
    max_sources: int = 3,
    excerpt_chars: int = 420,
) -> str:
    """Build a deterministic, cited answer when model repair fails closed."""

    statements: list[str] = []
    for source in sources[:max_sources]:
        source_id = str(source.get("source_id") or "").strip().upper()
        text = " ".join(str(source.get("text") or "").split())
        if not re.fullmatch(r"S\d+", source_id) or not text:
            continue
        text = re.sub(r"\[(?:S\d+)\]", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"[.!?]+(?:\s+|$)", ", ", text).strip(" ,")
        if len(text) > excerpt_chars:
            shortened = text[:excerpt_chars].rsplit(" ", 1)[0].rstrip(" ,;:")
            text = f"{shortened}…"
        locator = format_source_locator(source)
        prefix = "" if not statements else "- "
        statements.append(
            f"{prefix}Theo {locator} [{source_id}], "
            f"nguồn pháp lý truy hồi ghi nhận: {text} [{source_id}]."
        )
    return "\n".join(statements)


def _legal_answer_generation_policy(
    answer_plan: dict[str, Any],
) -> tuple[int, int, str]:
    """Keep simple answers concise while preserving room for complex coverage."""

    mode = str(answer_plan.get("mode") or "single_hop")
    if mode == "multi_abstract":
        return (
            2200,
            10,
            "Tối đa 900 từ. Chia theo các nhóm vấn đề thực sự có trong câu hỏi; "
            "mỗi nhóm chỉ nêu một lần và không lặp lại cùng căn cứ.",
        )
    if mode == "multi_hop":
        return (
            1400,
            8,
            "Tối đa 500 từ. Trả lời đủ từng vế, mỗi vế tối đa hai đoạn hoặc "
            "gạch đầu dòng; không lặp lại cùng kết luận, tỷ lệ hoặc công thức.",
        )
    return (
        900,
        6,
        "Từ 180 đến 300 từ, tối đa bốn đoạn hoặc gạch đầu dòng. Trả lời thẳng "
        "một lần, chỉ giữ công thức/điều kiện cần thiết và dùng số nguồn tối "
        "thiểu đủ chứng minh; tuyệt đối không diễn giải lặp lại cùng tỷ lệ, "
        "công thức hoặc kết luận.",
    )


async def _store_answer_cache_safely(
    answer_cache: SemanticAnswerCacheService,
    lookup: CacheLookup,
    answer: str,
    sources: list[dict[str, Any]],
    verification: dict[str, Any],
) -> None:
    """Persist cache after the HTTP response without making the user wait."""

    try:
        await answer_cache.store(
            lookup,
            answer,
            sources,
            verification,
        )
    except Exception:
        logger.exception("Cannot store semantic answer cache entry")


def _normalize_allowed_citation_syntax(
    value: str,
    allowed_ids: list[str],
) -> str:
    """Close harmless citation brackets without changing source identity.

    Gemini occasionally emits ``[S1.`` instead of ``[S1].``. Sending the
    entire legal prompt through a second generation just to restore that
    bracket adds tens of seconds. Only identifiers already present in the
    server-side allowlist are normalized; unknown or ambiguous identifiers
    still fail validation and use the guarded repair path.
    """

    allowed = {
        str(source_id).strip().upper()
        for source_id in allowed_ids
        if str(source_id).strip()
    }

    def close_bracket(match: re.Match[str]) -> str:
        source_id = f"{match.group(1)}{match.group(2)}".upper()
        if source_id not in allowed:
            return match.group(0)
        return f"[{source_id}]"

    return _UNCLOSED_CITATION_RE.sub(close_bracket, str(value or ""))


async def _complete_with_citation_repair(
    ai: GeminiService,
    system: str,
    prompt: str,
    *,
    allowed_ids: list[str],
    sources: list[dict[str, Any]] | None = None,
    max_tokens: int,
    temperature: float = 0.1,
) -> str:
    answer = await ai.complete(
        system,
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    normalized_answer = _normalize_allowed_citation_syntax(
        answer,
        allowed_ids,
    )
    if normalized_answer != answer:
        logger.info(
            "Normalized harmless citation punctuation without model repair"
        )
        answer = normalized_answer
    try:
        validate_citations(
            answer,
            allowed_ids,
            require_claim_coverage=True,
        )
        if sources is not None:
            _validate_grounded_legal_references(answer, sources)
            _validate_professional_legal_opening(answer)
        return answer
    except GeminiError as exc:
        logger.warning(
            "Initial legal answer validation failed reason=%s",
            " ".join(str(exc).split())[:500],
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
            validate_citations(
                repaired,
                allowed_ids,
                require_claim_coverage=True,
            )
            if sources is not None:
                _validate_grounded_legal_references(repaired, sources)
                _validate_professional_legal_opening(repaired)
            return repaired
        except Exception as exc:
            logger.warning(
                "Repaired legal answer validation failed reason=%s",
                " ".join(str(exc).split())[:500],
            )
            raise GeminiError(
                "Không thể tạo câu trả lời có căn cứ và trích dẫn hợp lệ."
            ) from exc
    except Exception as exc:
        logger.warning(
            "Citation validation failed closed error_type=%s",
            type(exc).__name__,
        )
        raise GeminiError(
            "Không thể xác minh căn cứ của câu trả lời."
        ) from exc


def _cache_verification_is_reusable(
    verification: dict[str, Any],
) -> bool:
    """Allow a fingerprint-validated cache when freshness is explicitly off."""

    if verification.get("checked") and verification.get("all_current"):
        return True
    return (
        str(verification.get("reason") or "").strip().lower()
        == "freshness_check_disabled"
    )


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
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(optional_user),
    settings: Settings = Depends(get_settings),
    retrieval: RetrievalService = Depends(retrieval_service),
    freshness: LegalFreshnessService = Depends(freshness_service),
    ai: GeminiService = Depends(ai_service),
    limiter: GuestRateLimiter = Depends(guest_rate_limiter),
    memory: ConversationMemoryService = Depends(conversation_memory_service),
    answer_cache: SemanticAnswerCacheService = Depends(semantic_answer_cache_service),
) -> ChatResponse:
    request_started = time.monotonic()
    cache_lookup_ms = 0
    retrieval_ms = 0
    generation_ms = 0
    persistence_ms = 0
    conversation: Conversation | None = None
    conversation_id: uuid.UUID | None = None
    authenticated_user_id = user.id if user else None
    cache_scope = f"user:{authenticated_user_id}" if authenticated_user_id else ""
    summary_context = ""
    # Client-provided history is only for an anonymous, temporary browser
    # session. Authenticated history always comes from PostgreSQL below.
    history_turns = [] if user else [(turn.role, turn.content) for turn in payload.history]
    if not user:
        guest_subject = _guest_rate_subject(request, response, settings)
        cache_scope = f"guest:{guest_subject}"
        try:
            await limiter.check(guest_subject)
        except GuestRateLimitExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except GuestRateLimitUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    if user:
        if payload.conversation_id:
            conversation = await _owned_conversation(db, payload.conversation_id, user)
            conversation_id = conversation.id
            summary_context = await memory.get_summary(db, conversation_id)
            history_turns = await _load_postgres_chat_history(db, conversation_id, settings)
        # Authentication and history reads must not retain a PostgreSQL
        # transaction while cache/search/Gemini network calls are in flight.
        await db.rollback()
        conversation = None
    elif payload.conversation_id:
        raise HTTPException(
            status_code=401,
            detail="Đăng nhập bằng Google để tiếp tục một cuộc trò chuyện đã lưu",
        )

    cache_lookup: CacheLookup | None = None
    cache_hit = False
    cache_similarity: float | None = None
    cache_mode = "miss"
    cached_draft = ""
    answer = ""
    sources: list[dict[str, Any]] = []
    verification: dict[str, Any] = {}
    cache_eligible = answer_cache.eligible(
        payload.message,
        has_conversation_context=bool(history_turns or summary_context),
    )
    if cache_eligible:
        # Only context-free public-law questions pass the privacy gate, so
        # their exact answers can be reused across authenticated and guest
        # sessions without sharing private conversation data.
        cache_scope = "public:legal"
        try:
            cache_lookup_started = time.monotonic()
            cache_lookup = await answer_cache.lookup(
                payload.message,
                scope=cache_scope,
                # A semantic miss needs an extra Vertex embedding before legal
                # retrieval. At the production RPM limit that added about
                # 13 seconds to every new question.
                allow_semantic=False,
            )
            cache_lookup_ms += round(
                (time.monotonic() - cache_lookup_started) * 1000
            )
        except Exception:
            logger.exception("Cannot query semantic answer cache")

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
            if (
                cached.exact_match
                and not settings.require_freshness_check
                and _cache_verification_is_reusable(cached.verification)
            ):
                # Reindex clears this cache and prompt/model revisions are part
                # of the lookup key, so an exact hit can skip legal retrieval
                # when live freshness checks are explicitly disabled.
                sources = cached.sources
                verification = cached.verification
                cache_similarity = cached.similarity
                answer = cached.answer
                cache_hit = True
                cache_mode = "exact"
                try:
                    await answer_cache.record_hit(cached.id)
                except Exception:
                    logger.exception("Cannot update semantic answer cache hit counter")
            else:
                retrieval_started = time.monotonic()
                current_sources, current_verification = await _legal_sources(
                    payload.message,
                    retrieval,
                    freshness,
                )
                retrieval_ms += round(
                    (time.monotonic() - retrieval_started) * 1000
                )
                fingerprint_matches = (
                    legal_fingerprint(current_sources, current_verification)
                    == cached.law_fingerprint
                )
                if (
                    _cache_verification_is_reusable(current_verification)
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
                        cache_mode = "exact"
                    else:
                        cached_draft = cached.answer
                        cache_mode = "semantic_draft"
                    try:
                        await answer_cache.record_hit(cached.id)
                    except Exception:
                        logger.exception(
                            "Cannot update semantic answer cache hit counter"
                        )
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

    if not cache_hit:
        if not sources:
            retrieval_started = time.monotonic()
            sources, verification = await _legal_sources(
                payload.message,
                retrieval,
                freshness,
            )
            retrieval_ms += round(
                (time.monotonic() - retrieval_started) * 1000
            )
        answer_plan = build_answer_plan(payload.message)
        max_tokens, max_model_sources, length_instruction = (
            _legal_answer_generation_policy(answer_plan)
        )
        model_sources = select_context_sources(
            sources[:max_model_sources],
            max_chars=24000,
        )
        generation_started = time.monotonic()
        try:
            answer = await _complete_with_citation_repair(
                ai,
                LEGAL_SYSTEM_PROMPT,
                "BỘ NHỚ TÓM TẮT:\n"
                f"{_summary_prompt(summary_context)}\n\n"
                f"LỊCH SỬ HỘI THOẠI GẦN ĐÂY:\n{_chat_history_prompt(history_turns)}\n\n"
                "KẾ HOẠCH PHỦ CÂU HỎI:\n"
                f"{untrusted_data_block('ANSWER_PLAN', answer_plan)}\n\n"
                f"GIỚI HẠN ĐỘ DÀI:\n{length_instruction}\n\n"
                f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\n"
                f"NGUỒN:\n{build_context(model_sources)}\n\n"
                f"CÂU HỎI HIỆN TẠI:\n{untrusted_data_block('CURRENT_QUESTION', payload.message)}"
                f"\n\nBẢN NHÁP CACHE THAM KHẢO:\n"
                f"{untrusted_data_block('CACHE_DRAFT', cached_draft) if cached_draft else '(Không có)'}\n"
                "Nếu có bản nháp, phải điều chỉnh theo đúng câu hỏi hiện tại; "
                "không được sao chép các kết luận không còn phù hợp.",
                allowed_ids=[source["source_id"] for source in model_sources],
                sources=model_sources,
                max_tokens=max_tokens,
            )
        except GeminiError as exc:
            logger.error(
                "Legal answer generation failed; returning grounded fallback "
                "error_type=%s reason=%s",
                type(exc).__name__,
                " ".join(str(exc).split())[:500],
            )
            answer = _grounded_source_fallback(sources)
            if not answer:
                raise
            validate_citations(
                answer,
                [source["source_id"] for source in sources],
                require_claim_coverage=True,
            )
            # This fallback is assembled only from server-retrieved excerpts.
            # An excerpt can legitimately cross-reference a law outside the
            # top-k set, so the model-hallucination guard does not apply here.
            _validate_professional_legal_opening(answer)
        generation_ms += round(
            (time.monotonic() - generation_started) * 1000
        )
        answer = append_detailed_citations(answer, sources)
        if cache_lookup and _cache_verification_is_reusable(verification):
            background_tasks.add_task(
                _store_answer_cache_safely,
                answer_cache,
                cache_lookup,
                answer,
                sources,
                verification,
            )
    message_id = uuid.uuid4()
    persistence_started = time.monotonic()
    if user:
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
        try:
            await memory.refresh(conversation_id)
        except Exception:
            # The full encrypted transcript is already durable. A later turn
            # retries every message after last_message_sequence automatically.
            logger.exception("Cannot refresh conversation summary for %s", conversation_id)
    persistence_ms += round(
        (time.monotonic() - persistence_started) * 1000
    )
    total_ms = round((time.monotonic() - request_started) * 1000)
    logger.info(
        "Legal chat completed cache_mode=%s cache_lookup_ms=%d retrieval_ms=%d "
        "generation_ms=%d persistence_ms=%d total_ms=%d source_count=%d "
        "answer_chars=%d",
        cache_mode,
        cache_lookup_ms,
        retrieval_ms,
        generation_ms,
        persistence_ms,
        total_ms,
        len(sources),
        len(answer),
    )
    return ChatResponse(
        conversation_id=conversation_id,
        message_id=message_id,
        answer=answer,
        sources=sources,
        verification=verification,
        temporary=conversation is None,
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
    user_id = user.id
    await db.rollback()
    template = payload.template_name or next(
        (item["name"] for item in CONTRACT_TEMPLATES if item["id"] == payload.template_id), "Hợp đồng"
    )
    query = f"Căn cứ pháp luật và điều kiện bắt buộc để soạn {template}: {payload.prompt[:3000]}"
    sources, verification = await _legal_sources(query, retrieval, freshness)
    draft = await ai.complete(
        CONTRACT_SYSTEM_PROMPT,
        f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\nNGUỒN:\n{build_context(sources)}\n\n"
        "Hãy soạn hợp đồng theo dữ liệu đầu vào dưới đây.\n"
        f"{untrusted_data_block('CONTRACT_REQUEST', {'template': template, 'requirements': payload.prompt})}\n"
        "Bao gồm căn cứ, định nghĩa, quyền/nghĩa vụ, thanh toán, vi phạm, "
        "chấm dứt, tranh chấp và phần ký.",
        max_tokens=5000,
        temperature=0.12,
    )
    validate_citations(
        draft,
        [source["source_id"] for source in sources],
        require_claim_coverage=True,
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
        metadata={"sources": sources, "verification": verification, "checklist": checklist},
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
    user_id = user.id
    await db.rollback()
    query = f"Rà soát hợp đồng và rủi ro pháp lý: {payload.title or ''} {payload.text[:5000]}"
    sources, verification = await _legal_sources(query, retrieval, freshness)
    result = await ai.complete_json(
        CONTRACT_SYSTEM_PROMPT,
        f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\n"
        f"NGUỒN:\n{build_context(sources)}\n\n"
        f"HỢP ĐỒNG:\n{untrusted_data_block('CONTRACT_TEXT', payload.text)}",
        schema=REVIEW_SCHEMA,
        max_tokens=4200,
    )
    allowed_ids = [source["source_id"] for source in sources]
    validate_citations(result, allowed_ids)
    _validate_narrative_claims(result["summary"], allowed_ids)
    _validate_narrative_claims(result["recommendations"], allowed_ids)
    artifact = await _save_artifact(
        db, user_id, settings, kind="CONTRACT_REVIEW", title=payload.title or "Kết quả review hợp đồng",
        content=result["summary"], metadata={**result, "sources": sources, "verification": verification},
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
    user_id = user.id
    await db.rollback()
    query = f"Rủi ro pháp lý khi sửa đổi hợp đồng: {payload.original_text[:2500]} {payload.revised_text[:2500]}"
    sources, verification = await _legal_sources(query, retrieval, freshness)
    result = await ai.complete_json(
        CONTRACT_SYSTEM_PROMPT,
        f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\nNGUỒN:\n{build_context(sources)}\n\n"
        f"BẢN GỐC:\n{untrusted_data_block('ORIGINAL_CONTRACT', payload.original_text)}\n\n"
        f"BẢN SỬA:\n{untrusted_data_block('REVISED_CONTRACT', payload.revised_text)}",
        schema=COMPARE_SCHEMA,
        max_tokens=4800,
    )
    allowed_ids = [source["source_id"] for source in sources]
    validate_citations(result, allowed_ids)
    _validate_narrative_claims(result["summary"], allowed_ids)
    _validate_narrative_claims(result["recommendation"], allowed_ids)
    result["similarity"] = round(difflib.SequenceMatcher(None, payload.original_text, payload.revised_text).ratio() * 100)
    artifact = await _save_artifact(
        db, user_id, settings, kind="CONTRACT_COMPARE", title="So sánh hợp đồng",
        content=result["summary"], metadata={**result, "sources": sources, "verification": verification},
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
