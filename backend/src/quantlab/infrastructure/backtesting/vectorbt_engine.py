"""vectorbt implementation of the ``BacktestEngine`` port.

Signals are shifted one bar before execution (they were computed on the closed
candle), stops/targets come from the strategy's ``OrderPlan`` as fractions of
price, and costs include commission, configured slippage and — because candles
store the real spread — half a spread per side.
"""

import math
from typing import Any, cast

import numpy as np
import pandas as pd
import vectorbt as vbt

from quantlab.application.ports import BacktestEngine
from quantlab.domain.backtest import BacktestMetrics, BacktestResult, CostModel, OrderPlan
from quantlab.domain.market import Timeframe

MAX_EQUITY_POINTS = 500
METRIC_CAP = 1000.0


def _safe(value: Any, cap: float = METRIC_CAP) -> float:
    """Convert engine output to a JSON-safe, bounded float."""
    number = float(value)
    if math.isnan(number):
        return 0.0
    return max(-cap, min(cap, number))


def _shift(series: pd.Series) -> pd.Series:
    return series.shift(1, fill_value=False)


class VectorbtBacktestEngine(BacktestEngine):
    """Vectorized portfolio simulation backed by vectorbt."""

    def __init__(self, initial_cash: float = 10_000.0) -> None:
        self._initial_cash = initial_cash

    def run(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        orders: OrderPlan,
        costs: CostModel,
        timeframe: Timeframe,
    ) -> BacktestResult:
        slippage = pd.Series(costs.slippage_pct, index=data.index)
        if costs.use_spread and "spread" in data.columns:
            half_spread = (data["spread"] / (2.0 * data["close"])).fillna(0.0)
            slippage = slippage + half_spread * costs.spread_mult

        portfolio = vbt.Portfolio.from_signals(
            close=data["close"],
            entries=_shift(signals["long_entry"]),
            exits=_shift(signals["long_exit"]),
            short_entries=_shift(signals["short_entry"]),
            short_exits=_shift(signals["short_exit"]),
            sl_stop=orders.sl_pct.shift(1) if orders.sl_pct is not None else None,
            tp_stop=orders.tp_pct.shift(1) if orders.tp_pct is not None else None,
            sl_trail=orders.trailing,
            fees=costs.commission_pct,
            slippage=slippage,
            init_cash=self._initial_cash,
            # Default sizing (all available cash) is the only mode vectorbt
            # supports for signal-driven position reversals; granular position
            # sizing arrives with the risk-management phase.
            freq=timeframe.delta,
        )
        return BacktestResult(
            metrics=self._metrics(portfolio),
            equity=self._equity(portfolio),
            trade_returns=self._trade_returns(portfolio),
        )

    def _metrics(self, portfolio: Any) -> BacktestMetrics:
        trades = portfolio.trades
        trade_count = int(trades.count())
        max_drawdown = abs(_safe(portfolio.max_drawdown()))
        total_return = _safe(portfolio.total_return())
        if trade_count > 0:
            expectancy = _safe(trades.pnl.mean())
            avg_trade_return = _safe(trades.returns.mean())
            win_rate = _safe(trades.win_rate())
            profit_factor = _safe(trades.profit_factor())
        else:
            expectancy = avg_trade_return = win_rate = profit_factor = 0.0
        recovery_factor = _safe(total_return / max_drawdown) if max_drawdown > 0 else 0.0
        return BacktestMetrics(
            total_return=total_return,
            cagr=_safe(portfolio.annualized_return()),
            profit_factor=profit_factor,
            sharpe=_safe(portfolio.sharpe_ratio()),
            sortino=_safe(portfolio.sortino_ratio()),
            calmar=_safe(portfolio.calmar_ratio()),
            max_drawdown=max_drawdown,
            recovery_factor=recovery_factor,
            expectancy=expectancy,
            win_rate=win_rate,
            avg_trade_return=avg_trade_return,
            trades=trade_count,
        )

    @staticmethod
    def _trade_returns(portfolio: Any) -> list[float]:
        trades = portfolio.trades
        if int(trades.count()) == 0:
            return []
        return [float(value) for value in trades.returns.values]

    @staticmethod
    def _equity(portfolio: Any) -> pd.Series:
        equity = cast(pd.Series, portfolio.value())
        if len(equity) > MAX_EQUITY_POINTS:
            step = int(np.ceil(len(equity) / MAX_EQUITY_POINTS))
            equity = equity.iloc[::step]
        return equity
