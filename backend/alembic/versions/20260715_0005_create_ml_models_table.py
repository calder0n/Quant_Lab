"""Create ml_models table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ml_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=5), nullable=False),
        sa.Column("target", sa.String(length=32), nullable=False),
        sa.Column("algorithm", sa.String(length=32), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("timeframe", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("artifact_path", sa.String(), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ml_models")),
    )
    op.create_index(op.f("ix_ml_models_kind"), "ml_models", ["kind"])
    op.create_index(op.f("ix_ml_models_algorithm"), "ml_models", ["algorithm"])
    op.create_index(op.f("ix_ml_models_status"), "ml_models", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_ml_models_status"), table_name="ml_models")
    op.drop_index(op.f("ix_ml_models_algorithm"), table_name="ml_models")
    op.drop_index(op.f("ix_ml_models_kind"), table_name="ml_models")
    op.drop_table("ml_models")
