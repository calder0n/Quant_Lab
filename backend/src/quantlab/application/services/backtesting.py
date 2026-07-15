"""Backtest orchestration: dataset → strategy plugin → engine → scored result."""

from datetime import datetime

import pandas as pd

from quantlab.application.ports import BacktestEngine, CandleStore
from quantlab.domain.backtest import BacktestChart, BacktestResult, ChartMarker, CostModel
from quantlab.domain.market import Symbol, Timeframe
from quantlab.strategies.base import SIGNAL_COLUMNS, ParamValue, Strategy
from quantlab.strategies.registry import StrategyRegistry

MIN_BARS = 50


def _floats(series: pd.Series) -> list[float]:
    return [round(float(value), 6) for value in series]


def build_chart(
    strategy: Strategy, data: pd.DataFrame, signals: pd.DataFrame, chart_bars: int
) -> BacktestChart:
    """Assemble the recent-window price chart with the strategy's own overlays.

    Signals and indicators are computed over the full ``data`` (so they are
    correct at the window edge) and then sliced to the last ``chart_bars`` bars.
    """
    window = data.iloc[-chart_bars:]
    index = window.index
    overlays = {
        name: [
            None if pd.isna(value) else round(float(value), 6) for value in series.reindex(index)
        ]
        for name, series in strategy.chart_overlays(data).items()
    }
    markers: dict[str, list[ChartMarker]] = {}
    for column in SIGNAL_COLUMNS:
        fired = signals[column].reindex(index).fillna(False).to_numpy()
        markers[column] = [
            ChartMarker(time=str(time), price=round(float(window["close"].loc[time]), 6))
            for time in index[fired]
        ]
    return BacktestChart(
        time=[str(time) for time in index],
        open=_floats(window["open"]),
        high=_floats(window["high"]),
        low=_floats(window["low"]),
        close=_floats(window["close"]),
        overlays=overlays,
        markers=markers,
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
    ) -> BacktestResult:
        if self._store.coverage(symbol, timeframe) is None:
            raise DataNotAvailableError(
                f"No local data for {symbol} {timeframe}; run a dataset sync first."
            )
        data = self._store.load(symbol, timeframe, start=start, end=end)
        if len(data) < MIN_BARS:
            raise DataNotAvailableError(
                f"Only {len(data)} bars available for {symbol} {timeframe} in that range."
            )
        strategy = self._registry.create(strategy_id, params)
        signals = strategy.generate_signals(data)
        orders = strategy.generate_orders(data, signals)
        result = self._engine.run(data, signals, orders, costs or CostModel(), timeframe)
        result.fitness = strategy.fitness(result.metrics)
        result.params = dict(strategy.params)
        if chart_bars:
            result.chart = build_chart(strategy, data, signals, chart_bars)
        return result
