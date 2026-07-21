"""Backtest orchestration: dataset → strategy plugin → engine → scored result."""

import math
from datetime import datetime

import numpy as np
import pandas as pd

from quantlab.application.ports import BacktestEngine, CandleStore
from quantlab.domain.backtest import (
    BacktestChart,
    BacktestResult,
    ChartMarker,
    CostModel,
    OrderPlan,
)
from quantlab.domain.market import PIP_SIZE, Symbol, Timeframe
from quantlab.strategies import indicators as ta
from quantlab.strategies.base import SIGNAL_COLUMNS, ParamValue, Strategy
from quantlab.strategies.registry import StrategyRegistry

MIN_BARS = 50


def _floats(series: pd.Series) -> list[float]:
    return [round(float(value), 6) for value in series]


def build_chart(
    strategy: Strategy,
    data: pd.DataFrame,
    signals: pd.DataFrame,
    chart_bars: int,
    orders: OrderPlan | None = None,
) -> BacktestChart:
    """Assemble a price chart covering the *whole* backtested range.

    When the range holds more than ``chart_bars`` bars, consecutive bars are
    aggregated (first open / max high / min low / last close) so the chart still
    spans the full period at a viewable resolution; ``downsample`` reports the
    aggregation factor. Markers snap to the aggregated bar that contains them
    but keep their exact price and SL/TP levels from the order plan. An RSI pane
    is always included (using the strategy's own ``rsi_period`` when it has one).
    """
    total = len(data)
    factor = max(1, math.ceil(total / chart_bars)) if chart_bars else 1
    index = data.index[::factor]
    if factor > 1:
        groups = np.arange(total) // factor
        window = pd.DataFrame(
            {
                "open": data["open"].groupby(groups).first().to_numpy(),
                "high": data["high"].groupby(groups).max().to_numpy(),
                "low": data["low"].groupby(groups).min().to_numpy(),
                "close": data["close"].groupby(groups).last().to_numpy(),
            },
            index=index,
        )
    else:
        window = data

    overlays = {
        name: [
            None if pd.isna(value) else round(float(value), 6) for value in series.reindex(index)
        ]
        for name, series in strategy.chart_overlays(data).items()
    }

    def exit_levels(time: object, price: float, is_long: bool) -> tuple[float | None, float | None]:
        if orders is None:
            return None, None
        direction = 1.0 if is_long else -1.0
        sl = tp = None
        if orders.sl_pct is not None and not pd.isna(orders.sl_pct.loc[time]):
            sl = round(price * (1 - direction * float(orders.sl_pct.loc[time])), 6)
        if orders.tp_pct is not None and not pd.isna(orders.tp_pct.loc[time]):
            tp = round(price * (1 + direction * float(orders.tp_pct.loc[time])), 6)
        return sl, tp

    markers: dict[str, list[ChartMarker]] = {}
    closes = data["close"].to_numpy()
    for column in SIGNAL_COLUMNS:
        fired_positions = np.flatnonzero(signals[column].fillna(False).to_numpy())
        entries: list[ChartMarker] = []
        for position in fired_positions:
            label = str(index[position // factor])  # aggregated bar holding this signal
            price = round(float(closes[position]), 6)
            if column in ("long_entry", "short_entry"):
                sl, tp = exit_levels(
                    data.index[position], price, is_long=column == "long_entry"
                )
                entries.append(ChartMarker(time=label, price=price, sl=sl, tp=tp))
            else:
                entries.append(ChartMarker(time=label, price=price))
        markers[column] = entries

    rsi_period = int(strategy.params.get("rsi_period", 14))
    rsi = ta.rsi(data["close"], rsi_period).reindex(index)
    oscillators = {
        f"RSI ({rsi_period})": [
            None if pd.isna(value) else round(float(value), 2) for value in rsi
        ]
    }

    return BacktestChart(
        time=[str(time) for time in index],
        open=_floats(window["open"]),
        high=_floats(window["high"]),
        low=_floats(window["low"]),
        close=_floats(window["close"]),
        overlays=overlays,
        markers=markers,
        oscillators=oscillators,
        downsample=factor,
    )


class DataNotAvailableError(LookupError):
    """Raised when the requested series is not stored locally (sync it first)."""


class BacktestService:
    """Runs one strategy over one locally stored dataset."""

    def __init__(
        self, store: CandleStore, registry: StrategyRegistry, engine: BacktestEngine
    ) -> None:
        self._store = store
        self._registry = registry
        self._engine = engine

    def run(
        self,
        strategy_id: str,
        symbol: Symbol,
        timeframe: Timeframe,
        params: dict[str, ParamValue] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        costs: CostModel | None = None,
        chart_bars: int | None = None,
        initial_cash: float | None = None,
        months: int | None = None,
    ) -> BacktestResult:
        coverage = self._store.coverage(symbol, timeframe)
        if coverage is None:
            raise DataNotAvailableError(
                f"No local data for {symbol} {timeframe}; run a dataset sync first."
            )
        # A months window is measured back from the most recent stored bar.
        if months is not None and start is None:
            start = (pd.Timestamp(coverage.end) - pd.DateOffset(months=months)).to_pydatetime()
        data = self._store.load(symbol, timeframe, start=start, end=end)
        data.attrs["pip_size"] = PIP_SIZE[symbol]  # lets order plans use pip distances
        if len(data) < MIN_BARS:
            raise DataNotAvailableError(
                f"Only {len(data)} bars available for {symbol} {timeframe} in that range."
            )
        strategy = self._registry.create(strategy_id, params)
        signals = strategy.generate_signals(data)
        orders = strategy.generate_orders(data, signals)
        result = self._engine.run(
            data, signals, orders, costs or CostModel(), timeframe, initial_cash=initial_cash
        )
        result.fitness = strategy.fitness(result.metrics)
        result.params = dict(strategy.params)
        if chart_bars:
            result.chart = build_chart(strategy, data, signals, chart_bars, orders)
        return result
