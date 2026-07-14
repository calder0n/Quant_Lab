"""Backtesting value objects: costs, order plans, metrics and results."""

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class CostModel:
    """Trading friction applied by the backtest engine.

    ``use_spread`` charges half the stored real spread per side (the candles
    are mid prices); ``spread_mult`` scales it for stress scenarios.
    ``commission_pct`` and ``slippage_pct`` are fractions of notional per side
    (0.0002 = 2 bps).
    """

    commission_pct: float = 0.0
    slippage_pct: float = 0.0
    use_spread: bool = True
    spread_mult: float = 1.0


@dataclass
class OrderPlan:
    """Per-bar execution plan produced by a strategy.

    ``sl_pct``/``tp_pct`` are stop/target distances as a *fraction of price*
    aligned to the candle index; ``None`` disables that exit.
    """

    sl_pct: pd.Series | None = None
    tp_pct: pd.Series | None = None
    trailing: bool = False
    size_pct: float = 1.0


@dataclass(frozen=True)
class BacktestMetrics:
    """The metric set every optimization objective is built from."""

    total_return: float = 0.0
    cagr: float = 0.0
    profit_factor: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    max_drawdown: float = 0.0
    recovery_factor: float = 0.0
    expectancy: float = 0.0
    win_rate: float = 0.0
    avg_trade_return: float = 0.0
    trades: int = 0


@dataclass
class BacktestResult:
    """Outcome of one strategy execution over one dataset.

    ``trade_returns`` holds the net return fraction of each closed trade in
    chronological order; Monte Carlo validation resamples this sequence.
    """

    metrics: BacktestMetrics
    equity: pd.Series
    fitness: float = 0.0
    params: dict[str, float | int | bool | str] = field(default_factory=dict)
    trade_returns: list[float] = field(default_factory=list)
