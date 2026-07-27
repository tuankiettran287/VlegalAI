"""Invalidate vectors created by the previous embedding provider.

The vector size remains 1024, but vectors from different embedding models
cannot share a similarity space. Legal chunks are repopulated by the reindex
job; summaries and answer-cache rows are derived data and will be regenerated.
Answer-cache rows also begin tracking the embedding model/revision so future
configuration changes cannot compare vectors from incompatible spaces.
"""

import sqlalchemy as sa
from alembic import op


revision = "20260727_0012"
down_revision = "20260724_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("TRUNCATE TABLE graphrag_chunk, graphrag_law_version")
    op.execute("DELETE FROM conversation_summary")
    op.execute("DELETE FROM legal_answer_cache")
    op.add_column(
        "legal_answer_cache",
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
    )
    op.add_column(
        "legal_answer_cache",
        sa.Column("embedding_revision", sa.String(length=255), nullable=False),
    )


def downgrade() -> None:
    # Previous-model vectors cannot be reconstructed safely.
    op.drop_column("legal_answer_cache", "embedding_revision")
    op.drop_column("legal_answer_cache", "embedding_model")
