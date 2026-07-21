"""Validation runs: walk-forward, Monte Carlo and stress testing.

A backtest that only won in-sample proves nothing. Each validator answers a
different question:

- Walk-forward: do freshly optimized parameters keep working on data the
  optimizer never saw?
- Monte Carlo: how sensitive is the outcome to the *order and sampling* of
  trades? (confidence intervals instead of a single equity curve)
- Stress: does the edge survive hostile execution (wider spreads, fees,
  slippage, randomly delayed fills)?
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from quantlab.domain.events import DomainEvent
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.optimization import StudyStatus


class ValidationKind(StrEnum):
    WALK_FORWARD = "walk_forward"
    MONTE_CARLO = "monte_carlo"
    STRESS = "stress"


@dataclass
class ValidationRun:
    """One validation execution; ``result`` holds the kind-specific report."""

    kind: ValidationKind
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    params: dict[str, float | int | bool | str] | None = None
    config: dict[str, Any] = field(default_factory=dict)
    status: StudyStatus = StudyStatus.PENDING
    result: dict[str, Any] | None = None
    message: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class StressScenario:
    """One hostile execution environment."""

    name: str
    spread_mult: float = 1.0
    commission_pct: float = 0.0
    slippage_pct: float = 0.0
    max_delay_bars: int = 0


DEFAULT_STRESS_SCENARIOS: tuple[StressScenario, ...] = (
    StressScenario(name="baseline"),
    StressScenario(name="spread_x2", spread_mult=2.0),
    StressScenario(name="spread_x3", spread_mult=3.0),
    StressScenario(name="commission_2bps", commission_pct=0.0002),
    StressScenario(name="slippage_2bps", slippage_pct=0.0002),
    StressScenario(name="random_delay_3", max_delay_bars=3),
    StressScenario(
        name="hostile_combo",
        spread_mult=2.0,
        commission_pct=0.0002,
        slippage_pct=0.0002,
        max_delay_bars=2,
    ),
)


@dataclass(frozen=True, kw_only=True)
class ValidationCompleted(DomainEvent):
    validation_id: uuid.UUID
    kind: ValidationKind
    strategy_id: str


@dataclass(frozen=True, kw_only=True)
class ValidationFailed(DomainEvent):
    validation_id: uuid.UUID
    kind: ValidationKind
    error: str
