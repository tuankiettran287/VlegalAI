from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    avatar_url: str | None = None
    role: str


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


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    verification: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=5000)
    conversation_id: uuid.UUID | None = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID | None = None
    message_id: uuid.UUID
    answer: str
    sources: list[SourceOut]
    verification: VerificationReport
    temporary: bool = False


class DraftContractRequest(BaseModel):
    prompt: str = Field(min_length=8, max_length=30000)
    template_id: str | None = None
    template_name: str | None = Field(default=None, max_length=160)


class ReviewContractRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    text: str = Field(min_length=20, max_length=120000)


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
