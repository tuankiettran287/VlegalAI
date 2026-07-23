"""Store LLM conversation summaries and BGE-M3 embeddings in PostgreSQL."""

from alembic import op
import sqlalchemy as sa


revision = "20260723_0005"
down_revision = "20260723_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE conversation_summary (
            id UUID PRIMARY KEY,
            conversation_id UUID NOT NULL
                REFERENCES conversation(id) ON DELETE CASCADE,
            summary_ciphertext TEXT NOT NULL,
            summary_hash VARCHAR(64) NOT NULL,
            source_message_count INTEGER NOT NULL,
            embedding_model VARCHAR(255) NOT NULL,
            embedding_revision VARCHAR(255) NOT NULL,
            embedding vector(1024) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_conversation_summary_conversation
                UNIQUE (conversation_id),
            CONSTRAINT ck_conversation_summary_message_count
                CHECK (source_message_count > 0)
        )
        """
    )
    op.create_index(
        "ix_conversation_summary_summary_hash",
        "conversation_summary",
        ["summary_hash"],
    )
    op.execute(
        """
        CREATE INDEX ix_conversation_summary_embedding_hnsw
        ON conversation_summary USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.drop_table("conversation_summary")
