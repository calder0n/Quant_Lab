"""Add broker_trade_id to trade_history.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "trade_history", sa.Column("broker_trade_id", sa.String(length=32), nullable=True)
    )
    op.create_index(
        "ix_trade_history_broker_trade_id", "trade_history", ["broker_trade_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_trade_history_broker_trade_id", table_name="trade_history")
    op.drop_column("trade_history", "broker_trade_id")
