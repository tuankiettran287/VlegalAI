"""Move runtime counters and coordination to PostgreSQL."""

from alembic import op
import sqlalchemy as sa


revision = "20260723_0004"
down_revision = "20260721_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guest_rate_limit",
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("window_kind", sa.String(8), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint(
            "subject_hash",
            "window_kind",
            "window_start",
            name="pk_guest_rate_limit",
        ),
        sa.CheckConstraint(
            "window_kind IN ('MINUTE', 'HOUR')",
            name="ck_guest_rate_limit_window_kind",
        ),
        sa.CheckConstraint(
            "request_count > 0",
            name="ck_guest_rate_limit_request_count",
        ),
    )
    op.create_index(
        "ix_guest_rate_limit_window_start",
        "guest_rate_limit",
        ["window_start"],
    )


def downgrade() -> None:
    op.drop_table("guest_rate_limit")
