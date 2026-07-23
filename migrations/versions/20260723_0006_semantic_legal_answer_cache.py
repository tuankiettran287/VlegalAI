"""Add a privacy-gated semantic answer cache on PostgreSQL/pgvector."""

from alembic import op


revision = "20260723_0006"
down_revision = "20260723_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE legal_answer_cache (
            id UUID PRIMARY KEY,
            query_hash VARCHAR(64) NOT NULL,
            query_ciphertext TEXT NOT NULL,
            answer_ciphertext TEXT NOT NULL,
            answer_hash VARCHAR(64) NOT NULL,
            query_embedding vector(1024) NOT NULL,
            sources JSONB NOT NULL,
            verification JSONB NOT NULL,
            law_fingerprint VARCHAR(64) NOT NULL,
            model_name VARCHAR(255) NOT NULL,
            prompt_version VARCHAR(64) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            hit_count BIGINT NOT NULL DEFAULT 0,
            last_hit_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_legal_answer_cache_hit_count CHECK (hit_count >= 0)
        )
        """
    )
    op.create_index(
        "ix_legal_answer_cache_query_hash",
        "legal_answer_cache",
        ["query_hash"],
        unique=True,
    )
    op.create_index(
        "ix_legal_answer_cache_answer_hash",
        "legal_answer_cache",
        ["answer_hash"],
    )
    op.create_index(
        "ix_legal_answer_cache_law_fingerprint",
        "legal_answer_cache",
        ["law_fingerprint"],
    )
    op.create_index(
        "ix_legal_answer_cache_expires_at",
        "legal_answer_cache",
        ["expires_at"],
    )
    op.execute(
        """
        CREATE INDEX ix_legal_answer_cache_embedding_hnsw
        ON legal_answer_cache USING hnsw (query_embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.drop_table("legal_answer_cache")
