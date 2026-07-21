"""Persistence models for optimization studies and trials."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from quantlab.infrastructure.db.base import Base


class OptimizationStudyRecord(Base):
    __tablename__ = "optimization_studies"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(5))
    optimizer: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(10), index=True)
    n_trials: Mapped[int] = mapped_column(Integer)
    trials_completed: Mapped[int] = mapped_column(Integer, default=0)
    objective: Mapped[dict[str, Any]] = mapped_column(JSON)
    best_score: Mapped[float | None] = mapped_column(Float)
    best_params: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    fixed_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    seed: Mapped[int | None] = mapped_column(Integer)
    range_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    range_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OptimizationTrialRecord(Base):
    __tablename__ = "optimization_trials"
    __table_args__ = (Index("ix_optimization_trials_study_score", "study_id", "score"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("optimization_studies.id", ondelete="CASCADE")
    )
    number: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict[str, Any]] = mapped_column(JSON)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)
    score: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
