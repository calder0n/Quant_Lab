"""Tests for quantlab.domain.market."""

from datetime import timedelta

from quantlab.domain.market import CANDLE_COLUMNS, Symbol, Timeframe


def test_all_required_symbols_exist() -> None:
    assert {s.value for s in Symbol} == {
        "EURUSD",
        "GBPUSD",
        "USDJPY",
        "AUDUSD",
        "XAUUSD",
        "NAS100",
        "SPX500",
        "US30",
    }


def test_every_timeframe_has_a_duration() -> None:
    assert Timeframe.M1.delta == timedelta(minutes=1)
    assert Timeframe.H4.delta == timedelta(hours=4)
    assert Timeframe.D1.delta == timedelta(days=1)
    assert all(tf.seconds > 0 for tf in Timeframe)


def test_candle_columns_are_stable() -> None:
    assert CANDLE_COLUMNS == ["open", "high", "low", "close", "volume", "spread"]
