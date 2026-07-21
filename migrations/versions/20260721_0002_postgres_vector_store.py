"""Replace the Qdrant vector store with PostgreSQL pgvector."""

from alembic import op
import sqlalchemy as sa


revision = "20260721_0002"
down_revision = "20260714_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE graphrag_chunk (
            chunk_id VARCHAR(255) PRIMARY KEY,
            doc_id VARCHAR(255) NOT NULL,
            node_id VARCHAR(255) NOT NULL,
            chunk_type VARCHAR(32) NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            path_label TEXT NOT NULL DEFAULT '',
            citation TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            token_count INTEGER NOT NULL DEFAULT 0,
            ordinal INTEGER NOT NULL DEFAULT 0,
            source_url TEXT,
            law_code VARCHAR(120),
            law_status VARCHAR(32),
            law_version INTEGER,
            embedding vector(1536) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.create_index("ix_graphrag_chunk_doc_id", "graphrag_chunk", ["doc_id"])
    op.create_index("ix_graphrag_chunk_node_id", "graphrag_chunk", ["node_id"])
    op.create_index("ix_graphrag_chunk_type", "graphrag_chunk", ["chunk_type"])
    op.execute(
        """
        CREATE INDEX ix_graphrag_chunk_search ON graphrag_chunk USING gin (
            to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(citation, '') || ' ' || coalesce(text, ''))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_graphrag_chunk_embedding_hnsw
        ON graphrag_chunk USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    op.drop_column("legal_chunk", "qdrant_point_id")


def downgrade() -> None:
    op.add_column("legal_chunk", sa.Column("qdrant_point_id", sa.String(80), nullable=True))
    op.drop_table("graphrag_chunk")
