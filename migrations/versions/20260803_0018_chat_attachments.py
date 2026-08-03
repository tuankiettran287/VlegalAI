"""Store encrypted chat attachment context and safe display metadata."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260803_0018"
down_revision = "20260730_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_message",
        sa.Column(
            "attachments",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "chat_message",
        sa.Column("attachment_context_ciphertext", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_message", "attachment_context_ciphertext")
    op.drop_column("chat_message", "attachments")
