"""Enforce one LegalDocument per normalized law code."""

import sqlalchemy as sa
from alembic import op


revision = "20260724_0008"
down_revision = "20260723_0007"
branch_labels = None
depends_on = None


NORMALIZED_CODE_SQL = (
    "upper(regexp_replace(btrim(code), '[[:space:]]+', '', 'g'))"
)


def upgrade() -> None:
    # Duplicate rows may contain independently verified versions and chunks.
    # Refuse to discard either automatically; an operator must reconcile them
    # before this non-destructive uniqueness migration can proceed.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM legal_document
                GROUP BY {NORMALIZED_CODE_SQL}
                HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION
                    'Cannot enforce normalized legal-document code uniqueness: duplicate codes require reconciliation';
            END IF;
        END
        $$;
        """
    )
    op.create_check_constraint(
        "ck_legal_document_code_not_blank",
        "legal_document",
        "btrim(code) <> ''",
    )
    op.create_index(
        "uq_legal_document_code_normalized",
        "legal_document",
        [sa.text(NORMALIZED_CODE_SQL)],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_legal_document_code_normalized",
        table_name="legal_document",
    )
    op.drop_constraint(
        "ck_legal_document_code_not_blank",
        "legal_document",
        type_="check",
    )
