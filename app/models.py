from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class User(TimestampMixin, Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(180), default="Người dùng")
    avatar_url: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(32), default="USER", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    identities: Mapped[list[SsoIdentity]] = relationship(back_populates="user", cascade="all, delete-orphan")
    conversations: Mapped[list[Conversation]] = relationship(back_populates="user", cascade="all, delete-orphan")


class SsoIdentity(TimestampMixin, Base):
    __tablename__ = "sso_identity"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_sso_issuer_subject"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    issuer: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(500))
    provider: Mapped[str] = mapped_column(String(80), default="google")
    claims: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    user: Mapped[User] = relationship(back_populates="identities")


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversation"
    __table_args__ = (Index("ix_conversation_user_updated", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(220), default="Cuộc trò chuyện mới")
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", index=True)
    retrieval_mode: Mapped[str] = mapped_column(String(32), default="HYBRID_RAG")

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_message"
    __table_args__ = (Index("ix_chat_message_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content_ciphertext: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    verification: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="COMPLETED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class LegalDocument(TimestampMixin, Base):
    __tablename__ = "legal_document"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_doc_id: Mapped[str | None] = mapped_column(String(220), unique=True)
    code: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(Text)
    issuer: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(Text)
    official_domain: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="UNKNOWN", index=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_code: Mapped[str | None] = mapped_column(String(120))
    checksum: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    verification_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    chunks: Mapped[list[LegalChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class LegalChunk(Base):
    __tablename__ = "legal_chunk"
    __table_args__ = (
        UniqueConstraint("document_id", "version", "ordinal", name="uq_legal_chunk_version_ordinal"),
        Index("ix_legal_chunk_document_version", "document_id", "version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legal_document.id", ondelete="CASCADE"), index=True)
    external_chunk_id: Mapped[str] = mapped_column(String(255), unique=True)
    node_id: Mapped[str] = mapped_column(String(255), index=True)
    chunk_type: Mapped[str] = mapped_column(String(32), default="article")
    title: Mapped[str] = mapped_column(Text)
    citation: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped[LegalDocument] = relationship(back_populates="chunks")


class Artifact(TimestampMixin, Base):
    __tablename__ = "artifact"
    __table_args__ = (Index("ix_artifact_user_updated", "user_id", "updated_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(220))
    content_ciphertext: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)


class Article(TimestampMixin, Base):
    __tablename__ = "article"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"), index=True)
    slug: Mapped[str] = mapped_column(String(240), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(100), default="Pháp luật")
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", index=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    web_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    view_count: Mapped[int] = mapped_column(BigInteger, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class SignaturePacket(TimestampMixin, Base):
    __tablename__ = "signature_packet"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(220))
    document_ciphertext: Mapped[str] = mapped_column(Text)
    document_hash: Mapped[str] = mapped_column(String(64), index=True)
    signers: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    audit_log: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(24), default="READY", index=True)


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"), index=True)
    message_ciphertext: Mapped[str] = mapped_column(Text)
    page: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
