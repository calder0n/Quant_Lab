"""Test data builders."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from quantlab.domain.market import Timeframe


def make_candles(start: datetime, count: int, timeframe: Timeframe = Timeframe.H1) -> pd.DataFrame:
    """Build a deterministic candle DataFrame in the platform format."""
    times = [start + i * timeframe.delta for i in range(count)]
    base = [1.0 + i * 0.001 for i in range(count)]
    return pd.DataFrame(
        {
            "open": base,
            "high": [value + 0.002 for value in base],
            "low": [value - 0.002 for value in base],
            "close": [value + 0.001 for value in base],
            "volume": [100 + i for i in range(count)],
            "spread": [0.0002] * count,
        },
        index=pd.DatetimeIndex(times, tz=UTC, name="time"),
    )


def make_market_data(
    bars: int = 600,
    start: datetime | None = None,
    timeframe: Timeframe = Timeframe.H1,
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic but realistic OHLCV: random walk + cycles, positive prices."""
    rng = np.random.default_rng(seed)
    begin = start if start is not None else utc(2024, 1, 1)
    times = pd.DatetimeIndex(
        [begin + i * timeframe.delta for i in range(bars)], tz=UTC, name="time"
    )
    cycles = 0.02 * np.sin(np.arange(bars) / 25.0) + 0.01 * np.sin(np.arange(bars) / 7.0)
    jumps = rng.normal(0.0, 0.012, bars) * (rng.random(bars) < 0.05)  # occasional shocks
    walk = np.cumsum(rng.normal(0.0, 0.003, bars) + jumps)
    close = 100.0 * np.exp(walk + cycles)
    open_ = np.concatenate([[close[0]], close[:-1]])
    wick = np.abs(rng.normal(0.0, 0.0015, bars)) * close
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - wick
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": rng.integers(50, 5000, bars),
            "spread": 0.0002 * close,
        },
        index=times,
    )


def utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


ONE_HOUR = timedelta(hours=1)
