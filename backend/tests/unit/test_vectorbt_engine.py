"""Tests for the vectorbt backtest engine adapter."""

import numpy as np
import pandas as pd

from quantlab.domain.backtest import CostModel, OrderPlan
from quantlab.domain.market import Timeframe
from quantlab.infrastructure.backtesting.vectorbt_engine import (
    MAX_EQUITY_POINTS,
    VectorbtBacktestEngine,
)
from tests.factories import make_market_data, utc


def make_signals(
    data: pd.DataFrame, entry_at: int | None = None, exit_at: int | None = None
) -> pd.DataFrame:
    signals = pd.DataFrame(
        False, index=data.index, columns=["long_entry", "long_exit", "short_entry", "short_exit"]
    )
    if entry_at is not None:
        signals.iloc[entry_at, signals.columns.get_loc("long_entry")] = True
    if exit_at is not None:
        signals.iloc[exit_at, signals.columns.get_loc("long_exit")] = True
    return signals


def trending_data(bars: int = 200) -> pd.DataFrame:
    data = make_market_data(bars)
    ramp = np.linspace(0.0, 0.5, bars)  # strong uptrend dominates the noise
    for column in ("open", "high", "low", "close"):
        data[column] = data[column] * np.exp(ramp)
    return data


def test_long_trade_in_uptrend_is_profitable() -> None:
    data = trending_data()
    engine = VectorbtBacktestEngine()
    result = engine.run(
        data,
        make_signals(data, entry_at=10, exit_at=190),
        OrderPlan(),  # no stops: pure signal exit
        CostModel(use_spread=False),
        Timeframe.H1,
    )
    assert result.metrics.trades == 1
    assert result.metrics.total_return > 0
    assert result.metrics.win_rate == 1.0
    assert result.metrics.max_drawdown >= 0
    assert result.equity.iloc[-1] > result.equity.iloc[0]


def test_signal_on_last_bar_cannot_execute() -> None:
    """The engine shifts signals one bar: a last-bar signal must be dropped."""
    data = trending_data(100)
    engine = VectorbtBacktestEngine()
    result = engine.run(
        data,
        make_signals(data, entry_at=99),
        OrderPlan(),
        CostModel(use_spread=False),
        Timeframe.H1,
    )
    assert result.metrics.trades == 0
    assert result.metrics.total_return == 0.0


def test_costs_reduce_returns() -> None:
    data = trending_data()
    signals = make_signals(data, entry_at=10, exit_at=190)
    engine = VectorbtBacktestEngine()
    free = engine.run(data, signals, OrderPlan(), CostModel(use_spread=False), Timeframe.H1)
    costly = engine.run(
        data,
        signals,
        OrderPlan(),
        CostModel(commission_pct=0.002, slippage_pct=0.002, use_spread=True),
        Timeframe.H1,
    )
    assert costly.metrics.total_return < free.metrics.total_return


def test_stop_loss_limits_downside() -> None:
    data = make_market_data(200, seed=7)
    crash = np.linspace(0.0, -0.4, 200)  # downtrend
    for column in ("open", "high", "low", "close"):
        data[column] = data[column] * np.exp(crash)
    sl = pd.Series(0.02, index=data.index)
    engine = VectorbtBacktestEngine()
    stopped = engine.run(
        data,
        make_signals(data, entry_at=10),
        OrderPlan(sl_pct=sl),
        CostModel(use_spread=False),
        Timeframe.H1,
    )
    unstopped = engine.run(
        data,
        make_signals(data, entry_at=10),
        OrderPlan(),
        CostModel(use_spread=False),
        Timeframe.H1,
    )
    assert stopped.metrics.total_return > unstopped.metrics.total_return
    assert stopped.metrics.trades == 1


def test_equity_is_downsampled() -> None:
    data = make_market_data(2000)
    engine = VectorbtBacktestEngine()
    result = engine.run(
        data, make_signals(data, entry_at=5, exit_at=1900), OrderPlan(), CostModel(), Timeframe.H1
    )
    assert len(result.equity) <= MAX_EQUITY_POINTS + 1
    assert result.equity.index[0] == utc(2024, 1, 1)


def test_position_reversal_long_to_short_is_supported() -> None:
    """Regression: strategies emit opposite entries while in a position."""
    data = make_market_data(300)
    signals = make_signals(data)
    signals.iloc[10, signals.columns.get_loc("long_entry")] = True
    signals.iloc[150, signals.columns.get_loc("short_entry")] = True  # reversal
    engine = VectorbtBacktestEngine()
    result = engine.run(data, signals, OrderPlan(), CostModel(), Timeframe.H1)
    assert result.metrics.trades >= 2


def test_no_signals_produce_flat_metrics() -> None:
    data = make_market_data(120)
    engine = VectorbtBacktestEngine()
    result = engine.run(data, make_signals(data), OrderPlan(), CostModel(), Timeframe.H1)
    assert result.metrics.trades == 0
    assert result.metrics.profit_factor == 0.0
    assert result.metrics.expectancy == 0.0
