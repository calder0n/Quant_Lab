"""Configurable objective function for optimization studies.

The score is a weighted sum of *normalized* metrics (each transform is bounded
so no single metric can dominate by scale), divided by the total absolute
weight, giving a score in roughly [-1, 1]. Hard constraints (minimum trades,
maximum drawdown) collapse the score to -1 so optimizers abandon that region.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import cast

from quantlab.domain.backtest import BacktestMetrics

PENALTY_SCORE = -1.0

NORMALIZERS: dict[str, Callable[[BacktestMetrics], float]] = {
    "profit_factor": lambda m: min(m.profit_factor, 3.0) / 3.0,
    "sharpe": lambda m: math.tanh(m.sharpe / 2.0),
    "sortino": lambda m: math.tanh(m.sortino / 3.0),
    "calmar": lambda m: math.tanh(m.calmar / 3.0),
    "max_drawdown": lambda m: 1.0 - min(m.max_drawdown, 1.0),
    "recovery_factor": lambda m: math.tanh(m.recovery_factor / 5.0),
    "expectancy": lambda m: math.tanh(m.expectancy / 100.0),
    "cagr": lambda m: math.tanh(m.cagr),
    "win_rate": lambda m: m.win_rate,
    "avg_trade": lambda m: math.tanh(m.avg_trade_return * 100.0),
    "trades": lambda m: min(m.trades / 100.0, 1.0),
    "total_return": lambda m: math.tanh(m.total_return),
}

DEFAULT_WEIGHTS: dict[str, float] = {
    "sharpe": 0.25,
    "sortino": 0.15,
    "calmar": 0.15,
    "profit_factor": 0.20,
    "max_drawdown": 0.10,
    "cagr": 0.10,
    "win_rate": 0.05,
}


class InvalidObjectiveError(ValueError):
    """Raised when an objective configuration references unknown metrics."""


@dataclass(frozen=True)
class ObjectiveConfig:
    """Weights over normalized metrics plus hard constraints."""

    weights: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    min_trades: int = 30
    max_drawdown_limit: float | None = None

    def __post_init__(self) -> None:
        unknown = set(self.weights) - set(NORMALIZERS)
        if unknown:
            raise InvalidObjectiveError(
                f"Unknown objective metrics: {sorted(unknown)}; valid: {sorted(NORMALIZERS)}"
            )
        if not self.weights or sum(abs(w) for w in self.weights.values()) == 0.0:
            raise InvalidObjectiveError("Objective needs at least one non-zero weight")

    def to_dict(self) -> dict[str, object]:
        return {
            "weights": dict(self.weights),
            "min_trades": self.min_trades,
            "max_drawdown_limit": self.max_drawdown_limit,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, object]) -> "ObjectiveConfig":
        weights_raw = raw.get("weights")
        weights = (
            {str(k): float(v) for k, v in cast(Mapping[str, float], weights_raw).items()}
            if weights_raw
            else dict(DEFAULT_WEIGHTS)
        )
        max_dd = raw.get("max_drawdown_limit")
        return cls(
            weights=weights,
            min_trades=int(cast(int, raw.get("min_trades", 30))),
            max_drawdown_limit=float(cast(float, max_dd)) if max_dd is not None else None,
        )


def compute_score(metrics: BacktestMetrics, config: ObjectiveConfig) -> float:
    """Score a backtest under the configured objective."""
    if metrics.trades < config.min_trades:
        return PENALTY_SCORE
    if config.max_drawdown_limit is not None and metrics.max_drawdown > config.max_drawdown_limit:
        return PENALTY_SCORE
    total_weight = sum(abs(weight) for weight in config.weights.values())
    weighted = sum(weight * NORMALIZERS[name](metrics) for name, weight in config.weights.items())
    return weighted / total_weight
