"""Causal feature matrix shared by supervised ML and the RL environment.

Every feature is computed from information available at the close of each bar
(rolling windows never look forward), so a row at time t may be used to
predict anything strictly after t.
"""

import numpy as np
import pandas as pd

from quantlab.strategies import indicators as ta

WARMUP_BARS = 60  # longest lookback used below


def build_features(data: pd.DataFrame) -> pd.DataFrame:
    """Return the feature matrix aligned to ``data`` (first rows contain NaN)."""
    assert isinstance(data.index, pd.DatetimeIndex)
    close = data["close"]
    atr = ta.atr(data, 14)
    atr_safe = atr.replace(0.0, np.nan)

    features = pd.DataFrame(index=data.index)
    features["ret_1"] = close.pct_change(1)
    features["ret_5"] = close.pct_change(5)
    features["ret_20"] = close.pct_change(20)
    features["rsi_14"] = ta.rsi(close, 14) / 100.0
    features["atr_norm"] = atr / close
    features["ema_20_dist"] = (close - ta.ema(close, 20)) / atr_safe
    features["ema_50_dist"] = (close - ta.ema(close, 50)) / atr_safe
    features["bb_z"] = ta.zscore(close, 20)
    features["vol_z"] = ta.zscore(data["volume"].astype(float), 50)

    hours = pd.Series(data.index.hour, index=data.index, dtype=float)
    features["hour_sin"] = np.sin(2.0 * np.pi * hours / 24.0)
    features["hour_cos"] = np.cos(2.0 * np.pi * hours / 24.0)

    candle_range = (data["high"] - data["low"]).replace(0.0, np.nan)
    features["body_ratio"] = (data["close"] - data["open"]) / candle_range
    features["upper_wick"] = (data["high"] - data[["open", "close"]].max(axis=1)) / candle_range
    features["lower_wick"] = (data[["open", "close"]].min(axis=1) - data["low"]) / candle_range

    if "spread" in data.columns:
        features["spread_norm"] = (data["spread"] / close) * 10_000.0  # in bps
    else:
        features["spread_norm"] = 0.0
    return features


def feature_names() -> list[str]:
    """Stable feature order (used to persist alongside model artifacts)."""
    return [
        "ret_1",
        "ret_5",
        "ret_20",
        "rsi_14",
        "atr_norm",
        "ema_20_dist",
        "ema_50_dist",
        "bb_z",
        "vol_z",
        "hour_sin",
        "hour_cos",
        "body_ratio",
        "upper_wick",
        "lower_wick",
        "spread_norm",
    ]
