"""Create auto_traders table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auto_traders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("timeframe", sa.String(length=5), nullable=False),
        sa.Column("units", sa.Float(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_bucket", sa.BigInteger(), nullable=True),
        sa.Column("last_run", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_signal_time", sa.String(length=40), nullable=True),
        sa.Column("last_action", sa.String(length=20), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auto_traders")),
    )
    op.create_index(op.f("ix_auto_traders_strategy_id"), "auto_traders", ["strategy_id"])
    op.create_index(op.f("ix_auto_traders_enabled"), "auto_traders", ["enabled"])


def downgrade() -> None:
    op.drop_index(op.f("ix_auto_traders_enabled"), table_name="auto_traders")
    op.drop_index(op.f("ix_auto_traders_strategy_id"), table_name="auto_traders")
    op.drop_table("auto_traders")
