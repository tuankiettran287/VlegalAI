"""Add deterministic per-conversation message cursors."""

from alembic import op


revision = "20260723_0007"
down_revision = "20260723_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_message
        ADD COLUMN message_sequence BIGINT
        """
    )
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY conversation_id
                    ORDER BY
                        created_at,
                        CASE role
                            WHEN 'USER' THEN 0
                            WHEN 'ASSISTANT' THEN 1
                            ELSE 2
                        END,
                        id
                ) AS message_sequence
            FROM chat_message
        )
        UPDATE chat_message AS message
        SET message_sequence = ranked.message_sequence
        FROM ranked
        WHERE message.id = ranked.id
        """
    )
    op.execute(
        """
        ALTER TABLE chat_message
        ALTER COLUMN message_sequence SET NOT NULL
        """
    )
    op.create_unique_constraint(
        "uq_chat_message_conversation_sequence",
        "chat_message",
        ["conversation_id", "message_sequence"],
    )

    op.execute(
        """
        ALTER TABLE conversation_summary
        ADD COLUMN last_message_sequence BIGINT
        """
    )
    op.execute(
        """
        -- Existing summaries were built against created_at/id ordering. Once
        -- deterministic role-aware sequences are introduced, retaining their
        -- old numeric cursor could skip a message. Summaries are derivative;
        -- invalidate them so the next turn rebuilds from the encrypted
        -- transcript without losing or duplicating a turn.
        DELETE FROM conversation_summary
        """
    )
    op.execute(
        """
        ALTER TABLE conversation_summary
        ALTER COLUMN last_message_sequence SET NOT NULL
        """
    )
    op.create_check_constraint(
        "ck_conversation_summary_last_message_sequence",
        "conversation_summary",
        "last_message_sequence > 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_conversation_summary_last_message_sequence",
        "conversation_summary",
        type_="check",
    )
    op.drop_column("conversation_summary", "last_message_sequence")
    op.drop_constraint(
        "uq_chat_message_conversation_sequence",
        "chat_message",
        type_="unique",
    )
    op.drop_column("chat_message", "message_sequence")
