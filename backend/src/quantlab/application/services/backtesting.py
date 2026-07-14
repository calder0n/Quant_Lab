"""Backtest orchestration: dataset → strategy plugin → engine → scored result."""

from datetime import datetime

from quantlab.application.ports import BacktestEngine, CandleStore
from quantlab.domain.backtest import BacktestResult, CostModel
from quantlab.domain.market import Symbol, Timeframe
from quantlab.strategies.base import ParamValue
from quantlab.strategies.registry import StrategyRegistry

MIN_BARS = 50


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
        return result
