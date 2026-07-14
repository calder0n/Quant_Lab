"""Test data builders."""

from datetime import UTC, datetime, timedelta

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


def utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)


ONE_HOUR = timedelta(hours=1)
