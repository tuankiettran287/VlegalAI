from __future__ import annotations

import difflib
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, select
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
    ConversationOut,
    ConversationUpdate,
    DraftContractRequest,
    FeedbackRequest,
    MessageOut,
    PrepareSignatureRequest,
    ReviewContractRequest,
)
from app.services.ai import CONTRACT_SYSTEM_PROMPT, LEGAL_SYSTEM_PROMPT, QwenError, QwenService
from app.services.articles import ArticleResearchService
from app.services.freshness import FreshnessUnavailable, LegalFreshnessService
from app.services.guest_limit import GuestRateLimitExceeded, GuestRateLimitUnavailable, GuestRateLimiter
from app.services.retrieval import RetrievalService, build_context


router = APIRouter()
router.include_router(auth_router)


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
        "summary": {"type": "string"},
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
                    "citations": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
}


COMPARE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "differences", "risks", "recommendation"],
    "properties": {
        "summary": {"type": "string"},
        "differences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "before", "after", "legal_impact"],
                "properties": {
                    "type": {"type": "string"},
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                    "legal_impact": {"type": "string"},
                },
            },
        },
        "risks": {"type": "array", "items": REVIEW_SCHEMA["properties"]["risks"]["items"]},
        "recommendation": {"type": "string"},
    },
}


def retrieval_service(request: Request) -> RetrievalService:
    return request.app.state.retrieval


def freshness_service(request: Request) -> LegalFreshnessService:
    return request.app.state.freshness


def ai_service(request: Request) -> QwenService:
    return request.app.state.ai


def article_research_service(request: Request) -> ArticleResearchService:
    return request.app.state.article_research


def guest_rate_limiter(request: Request) -> GuestRateLimiter:
    return request.app.state.guest_limiter


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


def _message_out(message: ChatMessage, settings: Settings) -> MessageOut:
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role.lower(),
        content=decrypt_text(message.content_ciphertext, settings),
        sources=message.sources,
        verification=message.verification,
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
    sources = await retrieval.retrieve(query)
    if not sources:
        raise HTTPException(status_code=404, detail="Chưa tìm thấy căn cứ pháp lý phù hợp trong chỉ mục")
    try:
        verification, updated = await freshness.verify_sources(sources)
    except FreshnessUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if updated:
        sources = await retrieval.retrieve(query)
        verification, _ = await freshness.verify_sources(sources)
    blocked_codes = {
        item.code.upper()
        for item in verification.items
        if item.status in {"EXPIRED", "REPLACED", "UNKNOWN"}
    }
    if blocked_codes:
        sources = [
            source
            for source in sources
            if not any(
                code in f"{source.get('citation', '')} {source.get('title', '')}".upper()
                for code in blocked_codes
            )
        ]
    if not sources:
        raise HTTPException(
            status_code=409,
            detail="Các căn cứ tìm thấy đã hết hiệu lực hoặc chưa xác minh được; chỉ mục mới chưa có đủ nguồn để trả lời an toàn.",
        )
    for index, source in enumerate(sources, start=1):
        source["source_id"] = f"S{index}"
    return sources, verification.model_dump(mode="json")


def _verification_prompt(verification: dict[str, Any]) -> str:
    return json.dumps(verification, ensure_ascii=False, indent=2)


def _chat_history_prompt(turns: list[tuple[str, str]]) -> str:
    if not turns:
        return "(Không có hội thoại trước đó)"
    labels = {"USER": "Người dùng", "ASSISTANT": "Trợ lý", "user": "Người dùng", "assistant": "Trợ lý"}
    return "\n".join(f"{labels.get(role, role)}: {content[:2000]}" for role, content in turns[-8:])


@router.get("/health/live", tags=["health"])
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
async def readiness(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    await db.scalar(select(func.now()))
    if not settings.qwen_ready:
        raise HTTPException(
            status_code=503,
            detail="Qwen offline checkpoint is not available",
        )
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


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    conversation = await _owned_conversation(db, conversation_id, user)
    messages = (
        await db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at)
        )
    ).all()
    return {"conversation": _conversation_out(conversation, len(messages)), "messages": [_message_out(row, settings) for row in messages]}


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
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(optional_user),
    settings: Settings = Depends(get_settings),
    retrieval: RetrievalService = Depends(retrieval_service),
    freshness: LegalFreshnessService = Depends(freshness_service),
    ai: QwenService = Depends(ai_service),
    limiter: GuestRateLimiter = Depends(guest_rate_limiter),
) -> ChatResponse:
    conversation: Conversation | None = None
    history_turns = [(turn.role, turn.content) for turn in payload.history]
    if not user:
        try:
            await limiter.check(_guest_rate_subject(request, response, settings))
        except GuestRateLimitExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except GuestRateLimitUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    if user:
        if payload.conversation_id:
            conversation = await _owned_conversation(db, payload.conversation_id, user)
            stored_history = (
                await db.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.conversation_id == conversation.id)
                    .order_by(ChatMessage.created_at.desc())
                    .limit(12)
                )
            ).all()
            history_turns = [
                (message.role, decrypt_text(message.content_ciphertext, settings))
                for message in reversed(stored_history)
            ]
        else:
            conversation = Conversation(
                user_id=user.id,
                title=payload.message[:100],
                retrieval_mode=settings.retriever_backend.upper(),
            )
            db.add(conversation)
            await db.flush()
        user_message = ChatMessage(
            conversation_id=conversation.id,
            role="USER",
            content_ciphertext=encrypt_text(payload.message, settings),
            content_hash=_hash_content(payload.message),
        )
        db.add(user_message)
        await db.commit()
    elif payload.conversation_id:
        raise HTTPException(
            status_code=401,
            detail="Đăng nhập bằng Google để tiếp tục một cuộc trò chuyện đã lưu",
        )

    sources, verification = await _legal_sources(payload.message, retrieval, freshness)
    answer = await ai.complete(
        LEGAL_SYSTEM_PROMPT,
        f"LỊCH SỬ HỘI THOẠI:\n{_chat_history_prompt(history_turns)}\n\n"
        f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\n"
        f"NGUỒN:\n{build_context(sources)}\n\nCÂU HỎI HIỆN TẠI:\n{payload.message}",
        max_tokens=2200,
    )
    message_id = uuid.uuid4()
    if conversation:
        assistant_message = ChatMessage(
            conversation_id=conversation.id,
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
    return ChatResponse(
        conversation_id=conversation.id if conversation else None,
        message_id=message_id,
        answer=answer,
        sources=sources,
        verification=verification,
        temporary=conversation is None,
    )


async def _save_artifact(
    db: AsyncSession,
    user: User,
    settings: Settings,
    *,
    kind: str,
    title: str,
    content: str,
    metadata: dict[str, Any],
) -> Artifact:
    artifact = Artifact(
        user_id=user.id,
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
    ai: QwenService = Depends(ai_service),
) -> dict[str, Any]:
    template = payload.template_name or next(
        (item["name"] for item in CONTRACT_TEMPLATES if item["id"] == payload.template_id), "Hợp đồng"
    )
    query = f"Căn cứ pháp luật và điều kiện bắt buộc để soạn {template}: {payload.prompt[:3000]}"
    sources, verification = await _legal_sources(query, retrieval, freshness)
    draft = await ai.complete(
        CONTRACT_SYSTEM_PROMPT,
        f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\nNGUỒN:\n{build_context(sources)}\n\n"
        f"Hãy soạn {template}. Yêu cầu: {payload.prompt}\nBao gồm căn cứ, định nghĩa, quyền/nghĩa vụ, thanh toán, vi phạm, chấm dứt, tranh chấp và phần ký.",
        max_tokens=5000,
        temperature=0.12,
    )
    checklist = [
        "Điền và đối chiếu thông tin pháp lý của các bên.",
        "Kiểm tra thẩm quyền ký và tài liệu ủy quyền.",
        "Chốt các mốc bàn giao, nghiệm thu, thanh toán và thuế.",
        "Rà soát phạt vi phạm, bồi thường, chấm dứt và giải quyết tranh chấp.",
        "Luật sư kiểm tra bản cuối trước khi ký nếu giao dịch có giá trị hoặc rủi ro cao.",
    ]
    artifact = await _save_artifact(
        db, user, settings, kind="CONTRACT_DRAFT", title=template, content=draft,
        metadata={"sources": sources, "verification": verification, "checklist": checklist},
    )
    return {
        "artifact_id": str(artifact.id), "title": template, "draft": draft, "checklist": checklist,
        "sources": sources, "verification": verification, "model": settings.qwen_model,
    }


@router.post("/contracts/review")
async def review_contract(
    payload: ReviewContractRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    retrieval: RetrievalService = Depends(retrieval_service),
    freshness: LegalFreshnessService = Depends(freshness_service),
    ai: QwenService = Depends(ai_service),
) -> dict[str, Any]:
    query = f"Rà soát hợp đồng và rủi ro pháp lý: {payload.title or ''} {payload.text[:5000]}"
    sources, verification = await _legal_sources(query, retrieval, freshness)
    result = await ai.complete_json(
        CONTRACT_SYSTEM_PROMPT,
        f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\nNGUỒN:\n{build_context(sources)}\n\nHỢP ĐỒNG:\n{payload.text}",
        schema=REVIEW_SCHEMA,
        max_tokens=4200,
    )
    artifact = await _save_artifact(
        db, user, settings, kind="CONTRACT_REVIEW", title=payload.title or "Kết quả review hợp đồng",
        content=result["summary"], metadata={**result, "sources": sources, "verification": verification},
    )
    return {"artifact_id": str(artifact.id), **result, "sources": sources, "verification": verification, "model": settings.qwen_model}


@router.post("/contracts/compare")
async def compare_contracts(
    payload: CompareContractRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
    settings: Settings = Depends(get_settings),
    retrieval: RetrievalService = Depends(retrieval_service),
    freshness: LegalFreshnessService = Depends(freshness_service),
    ai: QwenService = Depends(ai_service),
) -> dict[str, Any]:
    query = f"Rủi ro pháp lý khi sửa đổi hợp đồng: {payload.original_text[:2500]} {payload.revised_text[:2500]}"
    sources, verification = await _legal_sources(query, retrieval, freshness)
    result = await ai.complete_json(
        CONTRACT_SYSTEM_PROMPT,
        f"KIỂM TRA HIỆU LỰC:\n{_verification_prompt(verification)}\n\nNGUỒN:\n{build_context(sources)}\n\n"
        f"BẢN GỐC:\n{payload.original_text}\n\nBẢN SỬA:\n{payload.revised_text}",
        schema=COMPARE_SCHEMA,
        max_tokens=4800,
    )
    result["similarity"] = round(difflib.SequenceMatcher(None, payload.original_text, payload.revised_text).ratio() * 100)
    artifact = await _save_artifact(
        db, user, settings, kind="CONTRACT_COMPARE", title="So sánh hợp đồng",
        content=result["summary"], metadata={**result, "sources": sources, "verification": verification},
    )
    return {"artifact_id": str(artifact.id), **result, "sources": sources, "verification": verification, "model": settings.qwen_model}


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
    result = await research.search(payload.query)
    if payload.save:
        article = Article(
            author_id=user.id,
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
