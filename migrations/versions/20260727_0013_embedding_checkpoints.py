"""Persist bulk embedding progress across Cloud Run Job attempts."""

import sqlalchemy as sa
from alembic import op


revision = "20260727_0013"
down_revision = "20260727_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "graphrag_embedding_checkpoint",
        sa.Column("chunk_id", sa.String(length=255), primary_key=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("embedding_revision", sa.String(length=255), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_graphrag_embedding_checkpoint_identity",
        "graphrag_embedding_checkpoint",
        [
            "embedding_model",
            "embedding_revision",
            "embedding_dimensions",
        ],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_graphrag_embedding_checkpoint_identity",
        table_name="graphrag_embedding_checkpoint",
    )
    op.drop_table("graphrag_embedding_checkpoint")
