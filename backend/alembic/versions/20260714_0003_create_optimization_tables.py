"""Create optimization studies and trials tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "optimization_studies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("timeframe", sa.String(length=5), nullable=False),
        sa.Column("optimizer", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("n_trials", sa.Integer(), nullable=False),
        sa.Column("trials_completed", sa.Integer(), nullable=False),
        sa.Column("objective", sa.JSON(), nullable=False),
        sa.Column("best_score", sa.Float(), nullable=True),
        sa.Column("best_params", sa.JSON(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("range_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("range_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_optimization_studies")),
    )
    op.create_index(op.f("ix_optimization_studies_strategy_id"), "optimization_studies", ["strategy_id"])
    op.create_index(op.f("ix_optimization_studies_status"), "optimization_studies", ["status"])
    op.create_table(
        "optimization_trials",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("study_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_optimization_trials")),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["optimization_studies.id"],
            name=op.f("fk_optimization_trials_study_id_optimization_studies"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_optimization_trials_study_score", "optimization_trials", ["study_id", "score"]
    )


def downgrade() -> None:
    op.drop_index("ix_optimization_trials_study_score", table_name="optimization_trials")
    op.drop_table("optimization_trials")
    op.drop_index(op.f("ix_optimization_studies_status"), table_name="optimization_studies")
    op.drop_index(op.f("ix_optimization_studies_strategy_id"), table_name="optimization_studies")
    op.drop_table("optimization_studies")
