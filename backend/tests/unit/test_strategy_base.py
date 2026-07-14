"""Tests for the Strategy base class: params, filters, orders, fitness."""

import pandas as pd
import pytest

from quantlab.domain.backtest import BacktestMetrics
from quantlab.strategies.base import InvalidParameterError, ParameterSpec, Strategy
from tests.factories import make_market_data


class DummyStrategy(Strategy):
    strategy_id = "dummy"
    name = "Dummy"
    description = "test strategy"
    PARAMS = (ParameterSpec("threshold", "float", 1.0, 0.0, 10.0),)

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        entry = data["close"] > data["close"].shift(1)
        return self._frame(data, long_entry=entry, long_exit=~entry)


def test_metadata_includes_own_and_risk_params() -> None:
    names = [spec.name for spec in DummyStrategy.metadata().parameters]
    assert "threshold" in names
    assert {"atr_period", "sl_atr", "tp_atr", "use_trailing", "session_start"} <= set(names)


def test_defaults_are_applied_and_overridable() -> None:
    assert DummyStrategy().params["threshold"] == 1.0
    assert DummyStrategy(threshold=2.5).params["threshold"] == 2.5


def test_unknown_parameter_is_rejected() -> None:
    with pytest.raises(InvalidParameterError, match="Unknown parameters"):
        DummyStrategy(nope=1)


def test_out_of_range_parameter_is_rejected() -> None:
    with pytest.raises(InvalidParameterError, match="above maximum"):
        DummyStrategy(threshold=99.0)
    with pytest.raises(InvalidParameterError, match="below minimum"):
        DummyStrategy(sl_atr=0.0)


def test_int_params_are_coerced() -> None:
    strategy = DummyStrategy(atr_period=20.0)
    assert strategy.params["atr_period"] == 20
    assert isinstance(strategy.params["atr_period"], int)


def test_session_filter_blocks_entries_outside_hours() -> None:
    data = make_market_data(48)
    strategy = DummyStrategy(session_start=8, session_end=12)
    signals = strategy.generate_signals(data)
    entry_hours = data.index[signals["long_entry"]].hour
    assert ((entry_hours >= 8) & (entry_hours <= 12)).all()


def test_session_filter_supports_overnight_wrap() -> None:
    data = make_market_data(48)
    strategy = DummyStrategy(session_start=22, session_end=2)
    signals = strategy.generate_signals(data)
    entry_hours = data.index[signals["long_entry"]].hour
    assert ((entry_hours >= 22) | (entry_hours <= 2)).all()


def test_spread_filter_blocks_abnormal_spread() -> None:
    data = make_market_data(200)
    data.loc[data.index[100], "spread"] = data["spread"].median() * 50
    strategy = DummyStrategy(max_spread_mult=3.0)
    signals = strategy.generate_signals(data)
    assert not signals["long_entry"].iloc[100]


def test_default_orders_scale_with_atr_params() -> None:
    data = make_market_data(200)
    tight = DummyStrategy(sl_atr=1.0, tp_atr=1.0)
    wide = DummyStrategy(sl_atr=4.0, tp_atr=8.0)
    tight_plan = tight.generate_orders(data, tight.generate_signals(data))
    wide_plan = wide.generate_orders(data, wide.generate_signals(data))
    assert tight_plan.sl_pct is not None and wide_plan.sl_pct is not None
    assert (wide_plan.sl_pct.iloc[50:] > tight_plan.sl_pct.iloc[50:]).all()
    assert wide_plan.trailing is False
    assert (
        DummyStrategy(use_trailing=True)
        .generate_orders(data, tight.generate_signals(data))
        .trailing
    )


def test_default_fitness_behaviour() -> None:
    strategy = DummyStrategy()
    assert strategy.fitness(BacktestMetrics(trades=0)) == -1.0
    good = BacktestMetrics(sharpe=2.0, sortino=3.0, calmar=2.0, profit_factor=2.0, trades=100)
    bad = BacktestMetrics(sharpe=-1.0, sortino=-1.0, calmar=-1.0, profit_factor=0.5, trades=100)
    assert strategy.fitness(good) > strategy.fitness(bad)
    few_trades = BacktestMetrics(sharpe=2.0, sortino=3.0, calmar=2.0, profit_factor=2.0, trades=3)
    assert strategy.fitness(good) > strategy.fitness(few_trades)
