"""ML/RL model registry entities."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from quantlab.domain.events import DomainEvent
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.optimization import StudyStatus


class ModelKind(StrEnum):
    ML = "ml"  # supervised: predict trade outcome probabilities / expected move
    RL = "rl"  # reinforcement learning policy


ML_ALGORITHMS = ("xgboost", "lightgbm", "catboost", "torch_mlp")
RL_ALGORITHMS = ("ppo",)
RL_TARGET = "policy"


@dataclass
class MlModel:
    """One trained (or training) model with its evaluation report."""

    kind: ModelKind
    target: str
    algorithm: str
    symbol: Symbol
    timeframe: Timeframe
    status: StudyStatus = StudyStatus.PENDING
    config: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] | None = None
    artifact_path: str | None = None
    message: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class ModelTrained(DomainEvent):
    model_id: uuid.UUID
    kind: ModelKind
    algorithm: str


@dataclass(frozen=True, kw_only=True)
class ModelTrainingFailed(DomainEvent):
    model_id: uuid.UUID
    kind: ModelKind
    error: str
