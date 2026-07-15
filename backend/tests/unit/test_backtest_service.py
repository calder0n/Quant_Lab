"""Tests for the backtest orchestration service (fake engine, real store/registry)."""

from pathlib import Path

import pandas as pd
import pytest

from quantlab.application.ports import BacktestEngine
from quantlab.application.services.backtesting import BacktestService, DataNotAvailableError
from quantlab.domain.backtest import BacktestMetrics, BacktestResult, CostModel, OrderPlan
from quantlab.domain.market import Symbol, Timeframe
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from quantlab.strategies.base import InvalidParameterError
from quantlab.strategies.registry import StrategyRegistry, UnknownStrategyError
from tests.factories import make_market_data


class FakeEngine(BacktestEngine):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def run(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        orders: OrderPlan,
        costs: CostModel,
        timeframe: Timeframe,
    ) -> BacktestResult:
        self.calls.append({"bars": len(data), "costs": costs, "timeframe": timeframe})
        return BacktestResult(
            metrics=BacktestMetrics(sharpe=1.5, profit_factor=1.8, trades=50),
            equity=pd.Series([10_000.0, 11_000.0], index=data.index[:2]),
        )


@pytest.fixture
def service(tmp_path: Path) -> tuple[BacktestService, FakeEngine]:
    store = ParquetCandleStore(tmp_path / "candles")
    store.append(Symbol.EURUSD, Timeframe.H1, make_market_data(300))
    engine = FakeEngine()
    return BacktestService(store, StrategyRegistry().discover(), engine), engine


def test_run_produces_scored_result(service: tuple[BacktestService, FakeEngine]) -> None:
    backtest_service, engine = service
    result = backtest_service.run("ema_cross", Symbol.EURUSD, Timeframe.H1)
    assert result.fitness != 0.0
    assert result.params["fast_period"] == 12  # defaults echoed back
    assert engine.calls[0]["bars"] == 300
    assert engine.calls[0]["timeframe"] == Timeframe.H1
    assert result.chart is None  # no chart unless requested


def test_run_builds_inspection_chart(service: tuple[BacktestService, FakeEngine]) -> None:
    backtest_service, _ = service
    result = backtest_service.run("ema_cross", Symbol.EURUSD, Timeframe.H1, chart_bars=120)
    chart = result.chart
    assert chart is not None
    assert len(chart.time) == len(chart.close) == 120  # windowed to the last N bars
    assert chart.overlays.keys() == {"EMA fast", "EMA slow"}
    assert len(chart.overlays["EMA fast"]) == 120
    assert set(chart.markers) == {"long_entry", "long_exit", "short_entry", "short_exit"}
    for points in chart.markers.values():
        for marker in points:
            assert marker.time in chart.time  # markers land on real candles


def test_chart_window_caps_at_available_bars(service: tuple[BacktestService, FakeEngine]) -> None:
    backtest_service, _ = service  # store holds 300 bars
    result = backtest_service.run("rsi", Symbol.EURUSD, Timeframe.H1, chart_bars=10_000)
    assert result.chart is not None
    assert len(result.chart.time) == 300
    assert result.chart.overlays == {}  # rsi is an oscillator: markers only


def test_run_passes_custom_costs(service: tuple[BacktestService, FakeEngine]) -> None:
    backtest_service, engine = service
    costs = CostModel(commission_pct=0.001)
    backtest_service.run("rsi", Symbol.EURUSD, Timeframe.H1, costs=costs)
    assert engine.calls[0]["costs"] == costs


def test_missing_dataset_raises(service: tuple[BacktestService, FakeEngine]) -> None:
    backtest_service, _ = service
    with pytest.raises(DataNotAvailableError, match="No local data"):
        backtest_service.run("ema_cross", Symbol.GBPUSD, Timeframe.H1)


def test_too_few_bars_raises(tmp_path: Path) -> None:
    store = ParquetCandleStore(tmp_path / "candles")
    store.append(Symbol.EURUSD, Timeframe.H1, make_market_data(20))
    backtest_service = BacktestService(store, StrategyRegistry().discover(), FakeEngine())
    with pytest.raises(DataNotAvailableError, match="Only 20 bars"):
        backtest_service.run("ema_cross", Symbol.EURUSD, Timeframe.H1)


def test_unknown_strategy_raises(service: tuple[BacktestService, FakeEngine]) -> None:
    backtest_service, _ = service
    with pytest.raises(UnknownStrategyError):
        backtest_service.run("nope", Symbol.EURUSD, Timeframe.H1)


def test_invalid_params_raise(service: tuple[BacktestService, FakeEngine]) -> None:
    backtest_service, _ = service
    with pytest.raises(InvalidParameterError):
        backtest_service.run("ema_cross", Symbol.EURUSD, Timeframe.H1, params={"bad": 1})
