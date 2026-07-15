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


@dataclass(frozen=True)
class ChartMarker:
    """A signal firing on the price chart (entry or exit)."""

    time: str
    price: float


@dataclass
class BacktestChart:
    """Price window plus the strategy's own indicator lines and signal markers.

    Lets the dashboard show *why* an entry fired: the candles of the asset, the
    price-scale indicators/filters the strategy uses (``overlays``) and the exact
    bars where each signal triggered (``markers``). Built over the most recent
    ``chart_bars`` bars; the backtest metrics still cover the full range.
    """

    time: list[str] = field(default_factory=list)
    open: list[float] = field(default_factory=list)
    high: list[float] = field(default_factory=list)
    low: list[float] = field(default_factory=list)
    close: list[float] = field(default_factory=list)
    overlays: dict[str, list[float | None]] = field(default_factory=dict)
    markers: dict[str, list[ChartMarker]] = field(default_factory=dict)


@dataclass
class BacktestResult:
    """Outcome of one strategy execution over one dataset.

    ``trade_returns`` holds the net return fraction of each closed trade in
    chronological order; Monte Carlo validation resamples this sequence.
    ``chart`` is populated only when a price window is requested for inspection.
    """

    metrics: BacktestMetrics
    equity: pd.Series
    fitness: float = 0.0
    params: dict[str, float | int | bool | str] = field(default_factory=dict)
    trade_returns: list[float] = field(default_factory=list)
    chart: BacktestChart | None = None
