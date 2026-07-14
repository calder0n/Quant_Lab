"""Create broker_settings table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broker_settings",
        sa.Column("broker", sa.String(length=32), nullable=False),
        sa.Column("api_token", sa.String(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("broker", name=op.f("pk_broker_settings")),
    )


def downgrade() -> None:
    op.drop_table("broker_settings")
