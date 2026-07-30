"""Store per-answer human feedback for HITL regeneration."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260730_0017"
down_revision = "20260729_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_answer_feedback",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "regenerated_message_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("rating", sa.String(length=8), nullable=False),
        sa.Column("comment_ciphertext", sa.Text(), nullable=True),
        sa.Column("question_ciphertext", sa.Text(), nullable=False),
        sa.Column("answer_ciphertext", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "rating IN ('GOOD', 'BAD')",
            name="ck_chat_answer_feedback_rating",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversation.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_message.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["regenerated_message_id"],
            ["chat_message.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "message_id",
            name="uq_chat_answer_feedback_message",
        ),
    )
    op.create_index(
        "ix_chat_answer_feedback_user_id",
        "chat_answer_feedback",
        ["user_id"],
    )
    op.create_index(
        "ix_chat_answer_feedback_conversation_id",
        "chat_answer_feedback",
        ["conversation_id"],
    )
    op.create_index(
        "ix_chat_answer_feedback_regenerated_message_id",
        "chat_answer_feedback",
        ["regenerated_message_id"],
    )
    op.create_index(
        "ix_chat_answer_feedback_rating",
        "chat_answer_feedback",
        ["rating"],
    )
    op.create_index(
        "ix_chat_answer_feedback_user_rating_updated",
        "chat_answer_feedback",
        ["user_id", "rating", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_chat_answer_feedback_user_rating_updated",
        table_name="chat_answer_feedback",
    )
    op.drop_index(
        "ix_chat_answer_feedback_rating",
        table_name="chat_answer_feedback",
    )
    op.drop_index(
        "ix_chat_answer_feedback_regenerated_message_id",
        table_name="chat_answer_feedback",
    )
    op.drop_index(
        "ix_chat_answer_feedback_conversation_id",
        table_name="chat_answer_feedback",
    )
    op.drop_index(
        "ix_chat_answer_feedback_user_id",
        table_name="chat_answer_feedback",
    )
    op.drop_table("chat_answer_feedback")
