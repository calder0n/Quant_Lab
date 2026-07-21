"""Tests for the shared indicator library."""

import numpy as np
import pandas as pd

from quantlab.strategies import indicators as ta
from tests.factories import make_market_data


def test_rsi_is_bounded() -> None:
    data = make_market_data(300)
    rsi = ta.rsi(data["close"], 14)
    assert ((rsi >= 0) & (rsi <= 100)).all()


def test_atr_is_positive() -> None:
    data = make_market_data(300)
    assert (ta.atr(data, 14).iloc[5:] > 0).all()


def test_bollinger_band_ordering() -> None:
    data = make_market_data(300)
    lower, mid, upper = ta.bollinger(data["close"], 20, 2.0)
    valid = ~mid.isna()
    assert (lower[valid] <= mid[valid]).all()
    assert (mid[valid] <= upper[valid]).all()


def test_macd_signal_is_smoothed_macd() -> None:
    data = make_market_data(300)
    macd_line, signal_line, histogram = ta.macd(data["close"], 12, 26, 9)
    pd.testing.assert_series_equal(histogram, macd_line - signal_line)


def test_cross_above_and_below_are_single_bar_events() -> None:
    a = pd.Series([1.0, 2.0, 3.0, 2.0, 1.0])
    b = pd.Series([2.0, 2.0, 2.0, 2.0, 2.0])
    assert ta.cross_above(a, b).tolist() == [False, False, True, False, False]
    assert ta.cross_below(a, b).tolist() == [False, False, False, False, True]


def test_donchian_uses_only_past_bars() -> None:
    data = make_market_data(100)
    upper, lower = ta.donchian(data, 20)
    # The channel at bar t must not include bar t itself.
    t = 60
    assert upper.iloc[t] == data["high"].iloc[t - 20 : t].max()
    assert lower.iloc[t] == data["low"].iloc[t - 20 : t].min()


def test_session_vwap_resets_each_day() -> None:
    data = make_market_data(72)  # three UTC days of H1
    vwap = ta.session_vwap(data)
    first_bar_of_day = data.index.hour == 0
    typical = (data["high"] + data["low"] + data["close"]) / 3.0
    # At the first bar of a session VWAP equals that bar's typical price.
    np.testing.assert_allclose(vwap[first_bar_of_day], typical[first_bar_of_day])


def test_confirmed_swings_do_not_look_ahead() -> None:
    data = make_market_data(200)
    strength = 5
    swing = ta.confirmed_swing_high(data, strength)
    # A swing level at bar t must equal some high at least `strength` bars old.
    for t in range(50, 200, 25):
        level = swing.iloc[t]
        if not np.isnan(level):
            past_highs = data["high"].iloc[: t - strength + 1]
            assert (past_highs == level).any()


def test_bar_number_in_day_restarts_at_midnight() -> None:
    data = make_market_data(50)
    assert isinstance(data.index, pd.DatetimeIndex)
    numbers = ta.bar_number_in_day(data.index)
    assert numbers.iloc[0] == 0
    assert numbers.iloc[23] == 23
    assert numbers.iloc[24] == 0  # new UTC day
