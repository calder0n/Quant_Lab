"""Optimization studies and trials: the core entities of the research lab."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from quantlab.domain.backtest import BacktestMetrics
from quantlab.domain.events import DomainEvent
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.objective import ObjectiveConfig


class StudyStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class OptimizationStudy:
    """One optimization run: a strategy explored over one dataset."""

    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    optimizer: str
    n_trials: int
    objective: ObjectiveConfig
    status: StudyStatus = StudyStatus.PENDING
    trials_completed: int = 0
    best_score: float | None = None
    best_params: dict[str, float | int | bool | str] | None = None
    seed: int | None = None
    range_start: datetime | None = None
    range_end: datetime | None = None
    message: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class OptimizationTrial:
    """One evaluated parameter set within a study."""

    study_id: uuid.UUID
    number: int
    params: dict[str, float | int | bool | str]
    score: float
    metrics: BacktestMetrics
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class StudyCompleted(DomainEvent):
    study_id: uuid.UUID
    strategy_id: str
    best_score: float
    trials: int


@dataclass(frozen=True, kw_only=True)
class StudyFailed(DomainEvent):
    study_id: uuid.UUID
    strategy_id: str
    error: str
