"""Tests for the Strategy base class: params, filters, orders, fitness."""

import pandas as pd
import pytest

from quantlab.domain.backtest import BacktestMetrics
from quantlab.strategies import indicators as ta
from quantlab.strategies.base import InvalidParameterError, ParameterSpec, Strategy
from tests.factories import make_market_data


class DummyStrategy(Strategy):
    strategy_id = "dummy"
    name = "Dummy"
    description = "test strategy"
    PARAMS = (ParameterSpec("threshold", "float", 1.0, 0.0, 10.0),)

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        entry = data["close"] > data["close"].shift(1)
        return self._frame(
            data, long_entry=entry, long_exit=~entry, short_entry=~entry, short_exit=entry
        )


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
    strategy = DummyStrategy(use_session_filter=True, session_start=8, session_end=12)
    signals = strategy.generate_signals(data)
    entry_hours = data.index[signals["long_entry"]].hour
    assert ((entry_hours >= 8) & (entry_hours <= 12)).all()


def test_session_filter_is_off_by_default() -> None:
    data = make_market_data(48)
    off = DummyStrategy(session_start=8, session_end=12)  # toggle not set → no effect
    on = DummyStrategy(use_session_filter=True, session_start=8, session_end=12)
    assert (
        off.generate_signals(data)["long_entry"].sum()
        > on.generate_signals(data)["long_entry"].sum()
    )


def test_session_filter_supports_overnight_wrap() -> None:
    data = make_market_data(48)
    strategy = DummyStrategy(use_session_filter=True, session_start=22, session_end=2)
    signals = strategy.generate_signals(data)
    entry_hours = data.index[signals["long_entry"]].hour
    assert ((entry_hours >= 22) | (entry_hours <= 2)).all()


def test_spread_filter_blocks_abnormal_spread_and_can_be_disabled() -> None:
    data = make_market_data(200)
    data.loc[data.index[100], "spread"] = data["spread"].median() * 50
    # on by default: the spread spike blocks that bar's entry
    assert not DummyStrategy(max_spread_mult=3.0).generate_signals(data)["long_entry"].iloc[100]
    # disabling the filter lets the entry through
    disabled = DummyStrategy(use_spread_filter=False).generate_signals(data)
    entry_at_spike = data["close"].iloc[100] > data["close"].iloc[99]
    assert bool(disabled["long_entry"].iloc[100]) == entry_at_spike


def test_trend_filter_is_directional() -> None:
    data = make_market_data(400)
    trend = ta.ema(data["close"], 200)
    strategy = DummyStrategy(use_trend_filter=True, trend_ema=200)
    signals = strategy.generate_signals(data)
    # longs only fire above the trend EMA, shorts only below it
    assert (data["close"][signals["long_entry"]] > trend[signals["long_entry"]]).all()
    assert (data["close"][signals["short_entry"]] < trend[signals["short_entry"]]).all()


def test_volatility_filter_blocks_quiet_bars() -> None:
    data = make_market_data(300)
    permissive = DummyStrategy(use_volatility_filter=True, min_atr_pct=0.0)
    strict = DummyStrategy(use_volatility_filter=True, min_atr_pct=0.02)  # 200 bps: very high
    assert permissive.generate_signals(data)["long_entry"].sum() > 0
    assert strict.generate_signals(data)["long_entry"].sum() == 0  # nothing that volatile


def test_trend_filter_adds_a_chart_overlay() -> None:
    data = make_market_data(300)
    assert "Trend EMA" not in DummyStrategy().chart_overlays(data)
    assert "Trend EMA" in DummyStrategy(use_trend_filter=True).chart_overlays(data)


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


def test_ml_filter_gates_entries_on_predicted_win_probability() -> None:
    data = make_market_data(200)
    baseline = DummyStrategy().generate_signals(data)["long_entry"].sum()
    assert baseline > 0

    # A predictor that scores every bar below the threshold blocks all entries;
    # one that scores every bar above keeps them. The predictor is injected the
    # same way the services do it, via ``data.attrs``.
    data.attrs["ml_predictor"] = lambda d: pd.Series(0.10, index=d.index)
    blocked = DummyStrategy(use_ml_filter=True, ml_threshold=0.5).generate_signals(data)
    assert blocked["long_entry"].sum() == 0

    data.attrs["ml_predictor"] = lambda d: pd.Series(0.90, index=d.index)
    allowed = DummyStrategy(use_ml_filter=True, ml_threshold=0.5).generate_signals(data)
    assert allowed["long_entry"].sum() == baseline

    # Enabled but no model attached: the filter is a no-op, not an error.
    del data.attrs["ml_predictor"]
    no_model = DummyStrategy(use_ml_filter=True, ml_threshold=0.5).generate_signals(data)
    assert no_model["long_entry"].sum() == baseline


def test_default_fitness_behaviour() -> None:
    strategy = DummyStrategy()
    assert strategy.fitness(BacktestMetrics(trades=0)) == -1.0
    good = BacktestMetrics(sharpe=2.0, sortino=3.0, calmar=2.0, profit_factor=2.0, trades=100)
    bad = BacktestMetrics(sharpe=-1.0, sortino=-1.0, calmar=-1.0, profit_factor=0.5, trades=100)
    assert strategy.fitness(good) > strategy.fitness(bad)
    few_trades = BacktestMetrics(sharpe=2.0, sortino=3.0, calmar=2.0, profit_factor=2.0, trades=3)
    assert strategy.fitness(good) > strategy.fitness(few_trades)
