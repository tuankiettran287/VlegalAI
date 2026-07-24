"""Scope semantic answer-cache entries to one user or guest session."""

import sqlalchemy as sa
from alembic import op


revision = "20260724_0009"
down_revision = "20260724_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "legal_answer_cache",
        sa.Column("cache_scope_hash", sa.String(length=64), nullable=True),
    )
    # This table is a rebuildable derivative. Legacy rows were shared across
    # users and cannot be assigned to a safe owner after the fact.
    op.execute("DELETE FROM legal_answer_cache")
    op.alter_column(
        "legal_answer_cache",
        "cache_scope_hash",
        existing_type=sa.String(length=64),
        nullable=False,
    )
    op.drop_index(
        "ix_legal_answer_cache_query_hash",
        table_name="legal_answer_cache",
    )
    op.create_index(
        "ix_legal_answer_cache_query_hash",
        "legal_answer_cache",
        ["query_hash"],
        unique=False,
    )
    op.create_index(
        "ix_legal_answer_cache_cache_scope_hash",
        "legal_answer_cache",
        ["cache_scope_hash"],
        unique=False,
    )
    op.create_index(
        "uq_legal_answer_cache_scope_query",
        "legal_answer_cache",
        ["cache_scope_hash", "query_hash"],
        unique=True,
    )


def downgrade() -> None:
    # Multiple scopes can legitimately contain the same query hash, so clear
    # this disposable cache before restoring the legacy global uniqueness.
    op.execute("DELETE FROM legal_answer_cache")
    op.drop_index(
        "uq_legal_answer_cache_scope_query",
        table_name="legal_answer_cache",
    )
    op.drop_index(
        "ix_legal_answer_cache_cache_scope_hash",
        table_name="legal_answer_cache",
    )
    op.drop_index(
        "ix_legal_answer_cache_query_hash",
        table_name="legal_answer_cache",
    )
    op.create_index(
        "ix_legal_answer_cache_query_hash",
        "legal_answer_cache",
        ["query_hash"],
        unique=True,
    )
    op.drop_column("legal_answer_cache", "cache_scope_hash")
