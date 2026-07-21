"""Create validations table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "validations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("timeframe", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validations")),
    )
    op.create_index(op.f("ix_validations_kind"), "validations", ["kind"])
    op.create_index(op.f("ix_validations_strategy_id"), "validations", ["strategy_id"])
    op.create_index(op.f("ix_validations_status"), "validations", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_validations_status"), table_name="validations")
    op.drop_index(op.f("ix_validations_strategy_id"), table_name="validations")
    op.drop_index(op.f("ix_validations_kind"), table_name="validations")
    op.drop_table("validations")
