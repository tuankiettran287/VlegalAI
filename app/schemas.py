from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.official_sources import official_legal_source_url


_LEGAL_SOURCE_CODE_RE = re.compile(
    r"\b(?:\d{1,4}/\d{4}/[A-Z\u0110][A-Z0-9\u0110.\-]*|"
    r"\d{1,4}/VBHN-[A-Z\u0110][A-Z0-9\u0110.\-]*)\b",
    re.IGNORECASE,
)


def legal_source_code(*labels: str) -> str | None:
    """Extract a legal-document code without guessing an external URL."""

    match = _LEGAL_SOURCE_CODE_RE.search(" ".join(labels).upper())
    if match is None:
        return None
    return match.group(0).upper()



class AuthCapabilities(BaseModel):
    google_login: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    preferred_name: str | None = None
    avatar_url: str | None = None
    role: str
    onboarding_required: bool = False


class UserProfileUpdate(BaseModel):
    preferred_name: str = Field(min_length=1, max_length=60)

    @field_validator("preferred_name")
    @classmethod
    def normalize_preferred_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Tên gọi không được để trống")
        allowed_punctuation = {" ", ".", "-", "'", "_"}
        if any(not (character.isalnum() or character in allowed_punctuation) for character in normalized):
            raise ValueError("Tên gọi chứa ký tự không được hỗ trợ")
        return normalized


class SourceOut(BaseModel):
    source_id: str = ""
    score: float = 0
    chunk_type: str = ""
    citation: str = ""
    title: str = ""
    text: str = ""
    reasons: list[str] = Field(default_factory=list)
    doc_id: str | None = None
    source_url: str | None = None
    document_code: str | None = None

    @model_validator(mode="after")
    def add_document_code(self) -> "SourceOut":
        if not self.document_code:
            self.document_code = legal_source_code(self.citation, self.title)
        if not self.source_url:
            self.source_url = official_legal_source_url(self.document_code)
        return self


class LegalDocumentSectionOut(BaseModel):
    citation: str
    title: str
    path_label: str = ""
    text: str
    chunk_type: str
    ordinal: int


class LegalDocumentDetailOut(BaseModel):
    code: str
    title: str
    document_type: str
    issuer: str = ""
    status: str
    source_url: str | None = None
    law_version: int | None = None
    focused: bool = False
    sections: list[LegalDocumentSectionOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


class VerificationItem(BaseModel):
    code: str
    title: str
    status: str
    checked_at: datetime
    source_url: str | None = None
    replacement_code: str | None = None
    index_updated: bool = False


class VerificationReport(BaseModel):
    checked: bool = False
    all_current: bool = False
    checked_at: datetime | None = None
    items: list[VerificationItem] = Field(default_factory=list)
    note: str = ""


class LegalCatalogDocument(BaseModel):
    law_code_normalized: str
    code: str
    title: str
    document_type: str
    issuer: str = ""
    source_url: str | None = None
    corpus_status: str
    resolved_status: str
    status_source: str
    status_conflict: bool = False
    metadata_verified: bool = False
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    replaced_by_code: str | None = None
    verified_at: datetime | None = None
    law_version: int | None = None
    chunk_count: int = 0
    indexed_at: datetime | None = None
    refreshed_at: datetime | None = None


class LegalCatalogList(BaseModel):
    items: list[LegalCatalogDocument] = Field(default_factory=list)
    total: int
    page: int
    page_size: int


class LegalCatalogStats(BaseModel):
    total: int
    by_type: dict[str, int] = Field(default_factory=dict)
    by_status: dict[str, int] = Field(default_factory=dict)
    metadata_quality: dict[str, int] = Field(default_factory=dict)
    as_of: datetime | None = None


class ConversationCreate(BaseModel):
    title: str = Field(default="Cuộc trò chuyện mới", min_length=1, max_length=220)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=220)
    status: Literal["ACTIVE", "ARCHIVED"] | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: str
    retrieval_mode: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ChatAttachment(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    kind: Literal["image", "document"]
    size_bytes: int = Field(ge=0, le=15 * 1024 * 1024)
    page_count: int | None = Field(default=None, ge=0, le=250)
    truncated: bool = False


class ChatAttachmentUploadOut(ChatAttachment):
    token: str = Field(min_length=20, max_length=300_000)
    preview: str = Field(default="", max_length=500)


class ChatAttachmentToken(BaseModel):
    token: str = Field(min_length=20, max_length=300_000)


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: Literal["user", "assistant"]
    content: str
    sources: list[SourceOut] = Field(default_factory=list)
    verification: VerificationReport | None = None
    attachments: list[ChatAttachment] = Field(default_factory=list)
    feedback_rating: Literal["good", "bad"] | None = None
    created_at: datetime


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    messages: list[MessageOut] = Field(default_factory=list)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=5000)
    conversation_id: uuid.UUID | None = None
    regenerate_from_message_id: uuid.UUID | None = None
    attachments: list[ChatAttachmentToken] = Field(default_factory=list, max_length=3)
    history: list[ChatTurn] = Field(
        default_factory=list,
        max_length=12,
        description="Temporary guest history only; authenticated history is loaded from PostgreSQL.",
    )


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID
    answer: str
    sources: list[SourceOut]
    verification: VerificationReport
    temporary: bool = False
    cache_hit: bool = False
    cache_similarity: float | None = None
    replaces_message_id: uuid.UUID | None = None
    cache_mode: Literal[
        "miss",
        "exact",
        "semantic_draft",
        "scope_clarification",
        "catalog",
        "greeting",
        "unsupported_official_catalog",
        "injection_blocked",
        "out_of_scope",
    ] = "miss"


class ChatAnswerFeedbackRequest(BaseModel):
    rating: Literal["good", "bad"]
    comment: str | None = Field(default=None, max_length=2000)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class ChatAnswerFeedbackOut(BaseModel):
    message_id: uuid.UUID
    rating: Literal["good", "bad"]
    regeneration_available: bool = False



class DraftContractRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=30000)
    template_id: str | None = None
    template_name: str | None = Field(default=None, max_length=160)
    source_text: str | None = Field(default=None, min_length=20, max_length=120000)


class ReviewContractRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    text: str = Field(min_length=20, max_length=120000)
    user_role: str | None = Field(default=None, max_length=240)

    @field_validator("title", "user_role", mode="before")
    @classmethod
    def normalize_review_labels(cls, value: Any) -> str | None:
        if value is None:
            return None
        normalized = " ".join(str(value).split()).strip()
        return normalized or None

    @field_validator("text", mode="before")
    @classmethod
    def normalize_review_text(cls, value: Any) -> str:
        return (
            str(value or "")
            .replace("\x00", "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )


class CompareContractRequest(BaseModel):
    original_title: str | None = Field(default=None, max_length=160)
    revised_title: str | None = Field(default=None, max_length=160)
    original_text: str = Field(min_length=20, max_length=120000)
    revised_text: str = Field(min_length=20, max_length=120000)


class ArtifactCreate(BaseModel):
    kind: Literal["CONTRACT_DRAFT", "CONTRACT_REVIEW", "CONTRACT_COMPARE", "LEGAL_NOTE"]
    title: str = Field(min_length=1, max_length=220)
    content: str = Field(min_length=1, max_length=200000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: Literal["DRAFT", "FINAL", "ARCHIVED"] = "DRAFT"


class ArtifactUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=220)
    content: str | None = Field(default=None, min_length=1, max_length=200000)
    metadata: dict[str, Any] | None = None
    status: Literal["DRAFT", "FINAL", "ARCHIVED"] | None = None


class ArtifactOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    content: str
    metadata: dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime


class PrepareSignatureRequest(BaseModel):
    title: str = Field(min_length=2, max_length=220)
    document_text: str = Field(min_length=5, max_length=200000)
    signers: list[str] = Field(default_factory=list, max_length=20)


class ArticleCreate(BaseModel):
    title: str = Field(min_length=3, max_length=500)
    excerpt: str = Field(default="", max_length=2000)
    content: str = Field(default="", max_length=200000)
    category: str = Field(default="Pháp luật", max_length=100)
    source_url: str | None = None
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] = "DRAFT"


class ArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=500)
    excerpt: str | None = Field(default=None, max_length=2000)
    content: str | None = Field(default=None, max_length=200000)
    category: str | None = Field(default=None, max_length=100)
    source_url: str | None = None
    status: Literal["DRAFT", "PUBLISHED", "ARCHIVED"] | None = None


class ArticleSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    save: bool = False


class FeedbackRequest(BaseModel):
    message: str = Field(min_length=3, max_length=5000)
    page: str | None = Field(default=None, max_length=160)
