"""Index normalized law codes and versions for indexed-corpus retrieval."""

from alembic import op


revision = "20260724_0010"
down_revision = "20260724_0009"
branch_labels = None
depends_on = None


INDEX_NAME = "ix_graphrag_chunk_law_code_version"
NORMALIZED_CODE = (
    "upper(regexp_replace(btrim(law_code), '[[:space:]]+', '', 'g'))"
)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE INDEX {INDEX_NAME}
        ON graphrag_chunk ({NORMALIZED_CODE}, law_version DESC)
        WHERE law_code IS NOT NULL AND law_version IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
