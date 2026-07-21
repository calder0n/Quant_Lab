"""Create trade_history table.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trade_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("timeframe", sa.String(length=5), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("units", sa.Float(), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("sl_price", sa.Float(), nullable=True),
        sa.Column("tp_price", sa.Float(), nullable=True),
        sa.Column("trailing_distance", sa.Float(), nullable=True),
        sa.Column("realized_pl", sa.Float(), nullable=True),
        sa.Column("order_id", sa.String(length=32), nullable=False),
        sa.Column("filled", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("signal_time", sa.String(length=40), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_history_strategy_id", "trade_history", ["strategy_id"])
    op.create_index("ix_trade_history_executed_at", "trade_history", ["executed_at"])


def downgrade() -> None:
    op.drop_index("ix_trade_history_executed_at", table_name="trade_history")
    op.drop_index("ix_trade_history_strategy_id", table_name="trade_history")
    op.drop_table("trade_history")
