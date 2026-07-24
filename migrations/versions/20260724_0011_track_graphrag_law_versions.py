"""Track the latest indexed GraphRAG version for each law."""

from alembic import op


revision = "20260724_0011"
down_revision = "20260724_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE graphrag_law_version (
            law_code_normalized VARCHAR(120) PRIMARY KEY,
            latest_version INTEGER NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO graphrag_law_version (
            law_code_normalized,
            latest_version,
            updated_at
        )
        SELECT
            upper(
                regexp_replace(
                    btrim(law_code),
                    '[[:space:]]+',
                    '',
                    'g'
                )
            ),
            max(law_version),
            now()
        FROM graphrag_chunk
        WHERE law_code IS NOT NULL AND law_version IS NOT NULL
        GROUP BY 1
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS graphrag_law_version")
