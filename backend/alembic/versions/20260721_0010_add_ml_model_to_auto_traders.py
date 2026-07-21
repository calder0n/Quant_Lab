"""Add ml_model_id to auto_traders.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("auto_traders", sa.Column("ml_model_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("auto_traders", "ml_model_id")
