"""Initial production schema for identity, history, legal index and CRUD."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260714_0001"
down_revision = None
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    op.create_table(
        "app_user",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(180), nullable=False),
        sa.Column("avatar_url", sa.Text()),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    op.create_index("ix_app_user_email", "app_user", ["email"], unique=True)
    op.create_index("ix_app_user_role", "app_user", ["role"])
    op.create_index("ix_app_user_is_active", "app_user", ["is_active"])

    op.create_table(
        "sso_identity",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False, server_default="google"),
        sa.Column("claims", postgresql.JSONB(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("issuer", "subject", name="uq_sso_issuer_subject"),
    )
    op.create_index("ix_sso_identity_user_id", "sso_identity", ["user_id"])

    op.create_table(
        "conversation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(220), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("retrieval_mode", sa.String(32), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_conversation_user_id", "conversation", ["user_id"])
    op.create_index("ix_conversation_status", "conversation", ["status"])
    op.create_index("ix_conversation_user_updated", "conversation", ["user_id", "updated_at"])

    op.create_table(
        "legal_document",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("external_doc_id", sa.String(220), unique=True),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("issuer", sa.String(255)),
        sa.Column("source_url", sa.Text()),
        sa.Column("official_domain", sa.String(255)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("replaced_by_code", sa.String(120)),
        sa.Column("checksum", sa.String(64)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verification_payload", postgresql.JSONB(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_legal_document_code", "legal_document", ["code"])
    op.create_index("ix_legal_document_status", "legal_document", ["status"])
    op.create_index("ix_legal_document_verified_at", "legal_document", ["verified_at"])

    op.create_table(
        "article",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="SET NULL")),
        sa.Column("slug", sa.String(240), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("web_sources", postgresql.JSONB(), nullable=False),
        sa.Column("view_count", sa.BigInteger(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        *timestamps(),
    )
    op.create_index("ix_article_author_id", "article", ["author_id"])
    op.create_index("ix_article_slug", "article", ["slug"], unique=True)
    op.create_index("ix_article_status", "article", ["status"])
    op.create_index("ix_article_published_at", "article", ["published_at"])

    op.create_table(
        "chat_message",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content_ciphertext", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("verification", postgresql.JSONB(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_chat_message_conversation_id", "chat_message", ["conversation_id"])
    op.create_index("ix_chat_message_content_hash", "chat_message", ["content_hash"])
    op.create_index("ix_chat_message_conversation_created", "chat_message", ["conversation_id", "created_at"])

    op.create_table(
        "legal_chunk",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("legal_document.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_chunk_id", sa.String(255), nullable=False, unique=True),
        sa.Column("node_id", sa.String(255), nullable=False),
        sa.Column("chunk_type", sa.String(32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("citation", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("qdrant_point_id", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("document_id", "version", "ordinal", name="uq_legal_chunk_version_ordinal"),
    )
    op.create_index("ix_legal_chunk_document_id", "legal_chunk", ["document_id"])
    op.create_index("ix_legal_chunk_node_id", "legal_chunk", ["node_id"])
    op.create_index("ix_legal_chunk_text_hash", "legal_chunk", ["text_hash"])
    op.create_index("ix_legal_chunk_document_version", "legal_chunk", ["document_id", "version"])

    op.create_table(
        "artifact",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(220), nullable=False),
        sa.Column("content_ciphertext", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_artifact_user_id", "artifact", ["user_id"])
    op.create_index("ix_artifact_kind", "artifact", ["kind"])
    op.create_index("ix_artifact_status", "artifact", ["status"])
    op.create_index("ix_artifact_user_updated", "artifact", ["user_id", "updated_at"])

    op.create_table(
        "signature_packet",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(220), nullable=False),
        sa.Column("document_ciphertext", sa.Text(), nullable=False),
        sa.Column("document_hash", sa.String(64), nullable=False),
        sa.Column("signers", postgresql.JSONB(), nullable=False),
        sa.Column("audit_log", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_signature_packet_user_id", "signature_packet", ["user_id"])
    op.create_index("ix_signature_packet_document_hash", "signature_packet", ["document_hash"])
    op.create_index("ix_signature_packet_status", "signature_packet", ["status"])

    op.create_table(
        "user_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("app_user.id", ondelete="SET NULL")),
        sa.Column("message_ciphertext", sa.Text(), nullable=False),
        sa.Column("page", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_user_feedback_user_id", "user_feedback", ["user_id"])

    op.execute(
        "CREATE INDEX ix_article_search ON article USING gin "
        "(to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(excerpt, '') || ' ' || coalesce(content, '')))"
    )
    op.execute(
        "CREATE INDEX ix_legal_document_search ON legal_document USING gin "
        "(to_tsvector('simple', coalesce(code, '') || ' ' || coalesce(title, '')))"
    )


def downgrade() -> None:
    for table in [
        "user_feedback", "signature_packet", "artifact", "legal_chunk", "chat_message",
        "article", "legal_document", "conversation", "sso_identity", "app_user",
    ]:
        op.drop_table(table)
