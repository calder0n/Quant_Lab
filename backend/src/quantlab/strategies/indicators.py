"""Vectorized technical indicators shared by strategy plugins.

All helpers are pure pandas/numpy, aligned to the input index, and only use
information available at each bar (rolling windows never look forward; swing
levels are delayed until confirmed).
"""

import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()


def rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0).ewm(alpha=1.0 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0.0)).ewm(alpha=1.0 / period, adjust=False).mean()
    rs = gain / loss.replace(0.0, np.nan)
    return (100.0 - 100.0 / (1.0 + rs)).fillna(50.0)


def macd(
    series: pd.Series, fast: int, slow: int, signal: int
) -> tuple[pd.Series, pd.Series, pd.Series]:
    macd_line = ema(series, fast) - ema(series, slow)
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line, macd_line - signal_line


def atr(data: pd.DataFrame, period: int) -> pd.Series:
    prev_close = data["close"].shift(1)
    true_range = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - prev_close).abs(),
            (data["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False).mean()


def bollinger(
    series: pd.Series, period: int, num_std: float
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(series, period)
    std = series.rolling(period).std()
    return mid - num_std * std, mid, mid + num_std * std


def zscore(series: pd.Series, period: int) -> pd.Series:
    mean = series.rolling(period).mean()
    std = series.rolling(period).std()
    return (series - mean) / std.replace(0.0, np.nan)


def donchian(data: pd.DataFrame, period: int) -> tuple[pd.Series, pd.Series]:
    """Highest high / lowest low of the *previous* ``period`` bars (no lookahead)."""
    upper = data["high"].rolling(period).max().shift(1)
    lower = data["low"].rolling(period).min().shift(1)
    return upper, lower


def session_vwap(data: pd.DataFrame) -> pd.Series:
    """Volume-weighted average price anchored at each UTC day open."""
    assert isinstance(data.index, pd.DatetimeIndex)
    typical = (data["high"] + data["low"] + data["close"]) / 3.0
    day = data.index.date
    cum_pv = (typical * data["volume"]).groupby(day).cumsum()
    cum_volume = data["volume"].groupby(day).cumsum()
    return cum_pv / cum_volume.replace(0, np.nan)


def cross_above(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a > b) & (a.shift(1) <= b.shift(1))


def cross_below(a: pd.Series, b: pd.Series) -> pd.Series:
    return (a < b) & (a.shift(1) >= b.shift(1))


def confirmed_swing_high(data: pd.DataFrame, strength: int) -> pd.Series:
    """Level of the last confirmed swing high.

    A swing high needs ``strength`` lower highs on each side, so it only
    becomes *known* ``strength`` bars after it happens; the series is shifted
    accordingly to avoid lookahead.
    """
    window = 2 * strength + 1
    center_max = data["high"].rolling(window, center=True).max()
    is_swing = data["high"] == center_max
    return data["high"].where(is_swing).shift(strength).ffill()


def confirmed_swing_low(data: pd.DataFrame, strength: int) -> pd.Series:
    """Level of the last confirmed swing low (see :func:`confirmed_swing_high`)."""
    window = 2 * strength + 1
    center_min = data["low"].rolling(window, center=True).min()
    is_swing = data["low"] == center_min
    return data["low"].where(is_swing).shift(strength).ffill()


def candle_body(data: pd.DataFrame) -> pd.Series:
    return (data["close"] - data["open"]).abs()


def bar_number_in_day(index: pd.DatetimeIndex) -> pd.Series:
    """0-based position of each bar within its UTC day."""
    return pd.Series(index, index=index).groupby(index.date).cumcount()
