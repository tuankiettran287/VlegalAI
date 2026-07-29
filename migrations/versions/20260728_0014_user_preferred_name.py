"""Add the user-chosen name used by the assistant."""

import sqlalchemy as sa
from alembic import op


revision = "20260728_0014"
down_revision = "20260727_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column("preferred_name", sa.String(length=60), nullable=True),
    )
    # Existing accounts have already completed the previous sign-in flow.
    # Preserve their current name while requiring onboarding for future users.
    op.execute(
        """
        UPDATE app_user
        SET preferred_name = LEFT(NULLIF(BTRIM(display_name), ''), 60)
        WHERE preferred_name IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("app_user", "preferred_name")
