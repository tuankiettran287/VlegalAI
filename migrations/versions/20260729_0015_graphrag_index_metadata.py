"""Track the authoritative GraphRAG embedding contract in one metadata row."""

import sqlalchemy as sa
from alembic import op


revision = "20260729_0015"
down_revision = "20260728_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "graphrag_index_metadata",
        sa.Column("index_name", sa.String(length=32), primary_key=True),
        sa.Column("embedding_provider", sa.String(length=32), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_revision", sa.String(length=255), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "chunk_count",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Scan only enough contracts to distinguish a trusted vector space from
    # mixed embeddings. This runs once during migration, not at app startup.
    op.execute(
        """
        WITH contracts AS (
            SELECT
                embedding_model,
                embedding_revision,
                vector_dims(embedding) AS embedding_dimensions
            FROM graphrag_chunk
            GROUP BY
                embedding_model,
                embedding_revision,
                vector_dims(embedding)
            LIMIT 2
        ),
        contract_summary AS (
            SELECT
                count(*) AS contract_count,
                min(embedding_model) AS embedding_model,
                min(embedding_revision) AS embedding_revision,
                min(embedding_dimensions) AS embedding_dimensions
            FROM contracts
        )
        INSERT INTO graphrag_index_metadata (
            index_name,
            embedding_provider,
            embedding_model,
            embedding_revision,
            embedding_dimensions,
            status,
            chunk_count
        )
        SELECT
            'active',
            CASE
                WHEN embedding_revision LIKE 'vertex-ai-%' THEN 'vertex'
                WHEN embedding_revision LIKE 'gemini-api-%' THEN 'gemini-api'
                ELSE 'unknown'
            END,
            embedding_model,
            embedding_revision,
            embedding_dimensions,
            CASE WHEN contract_count = 1 THEN 'ready' ELSE 'mixed' END,
            (SELECT count(*) FROM graphrag_chunk)
        FROM contract_summary
        WHERE contract_count > 0
        """
    )


def downgrade() -> None:
    op.drop_table("graphrag_index_metadata")
