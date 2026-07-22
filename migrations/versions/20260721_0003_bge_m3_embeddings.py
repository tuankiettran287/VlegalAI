"""Replace legacy hash vectors with BGE-M3 semantic embeddings.

Existing vectors cannot be converted between models or dimensions. The chunk
index is intentionally cleared and must be repopulated by the re-embedding job.
Application-owned legal documents remain untouched.
"""

from alembic import op


revision = "20260721_0003"
down_revision = "20260721_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE graphrag_chunk")
    op.execute("DROP INDEX IF EXISTS ix_graphrag_chunk_embedding_hnsw")
    op.execute("ALTER TABLE graphrag_chunk DROP COLUMN embedding")
    op.execute("ALTER TABLE graphrag_chunk ADD COLUMN embedding_model VARCHAR(255)")
    op.execute("ALTER TABLE graphrag_chunk ADD COLUMN embedding_revision VARCHAR(255)")
    op.execute("ALTER TABLE graphrag_chunk ADD COLUMN embedding vector(1024) NOT NULL")
    op.execute("ALTER TABLE graphrag_chunk ALTER COLUMN embedding_model SET NOT NULL")
    op.execute("ALTER TABLE graphrag_chunk ALTER COLUMN embedding_revision SET NOT NULL")
    op.execute(
        """
        CREATE INDEX ix_graphrag_chunk_embedding_hnsw
        ON graphrag_chunk USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.execute("TRUNCATE TABLE graphrag_chunk")
    op.execute("DROP INDEX IF EXISTS ix_graphrag_chunk_embedding_hnsw")
    op.execute("ALTER TABLE graphrag_chunk DROP COLUMN embedding")
    op.execute("ALTER TABLE graphrag_chunk DROP COLUMN embedding_model")
    op.execute("ALTER TABLE graphrag_chunk DROP COLUMN embedding_revision")
    op.execute("ALTER TABLE graphrag_chunk ADD COLUMN embedding vector(1536) NOT NULL")
    op.execute(
        """
        CREATE INDEX ix_graphrag_chunk_embedding_hnsw
        ON graphrag_chunk USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
