"""Seed (or remove) a synthetic demo dataset: EURUSD H1, clearly marked "synthetic".

Lets you exercise the backtest lab without an OANDA token. Remove it before
syncing real data for the same series, or the two sources would be mixed:

    python scripts/seed_demo.py           # create
    python scripts/seed_demo.py --remove  # delete parquet + catalog row
"""

import argparse
import asyncio
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from quantlab.config import Settings
from quantlab.container import Container
from quantlab.domain.datasets import Dataset, DatasetStatus
from quantlab.domain.market import Symbol, Timeframe

DEMO_SYMBOL = Symbol.EURUSD
DEMO_TIMEFRAME = Timeframe.H1
BARS = 5000


def synthetic_candles(bars: int, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    times = pd.DatetimeIndex(
        [datetime(2024, 1, 1, tzinfo=UTC) + i * DEMO_TIMEFRAME.delta for i in range(bars)],
        tz=UTC,
        name="time",
    )
    cycles = 0.02 * np.sin(np.arange(bars) / 25.0) + 0.01 * np.sin(np.arange(bars) / 7.0)
    jumps = rng.normal(0.0, 0.012, bars) * (rng.random(bars) < 0.05)
    close = 1.10 * np.exp(np.cumsum(rng.normal(0.0, 0.001, bars) + jumps) + cycles)
    open_ = np.concatenate([[close[0]], close[:-1]])
    wick = np.abs(rng.normal(0.0, 0.0005, bars)) * close
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + wick,
            "low": np.minimum(open_, close) - wick,
            "volume": rng.integers(50, 5000, bars),
            "spread": 0.00013 * np.ones(bars),
            "close": close,
        },
        index=times,
    )[["open", "high", "low", "close", "volume", "spread"]]


async def seed(container: Container) -> None:
    coverage = container.candle_store.append(DEMO_SYMBOL, DEMO_TIMEFRAME, synthetic_candles(BARS))
    async with container.dataset_repository() as repo:
        await repo.upsert(
            Dataset(
                symbol=DEMO_SYMBOL,
                timeframe=DEMO_TIMEFRAME,
                status=DatasetStatus.READY,
                candle_count=coverage.candle_count,
                start_at=coverage.start,
                end_at=coverage.end,
                source="synthetic",
                path=str(container.candle_store.path_for(DEMO_SYMBOL, DEMO_TIMEFRAME)),
            )
        )
    print(f"Seeded {coverage.candle_count} synthetic candles: {DEMO_SYMBOL} {DEMO_TIMEFRAME}")


async def remove(container: Container) -> None:
    path = container.candle_store.path_for(DEMO_SYMBOL, DEMO_TIMEFRAME)
    if path.exists():
        path.unlink()
    async with container.dataset_repository() as repo:
        dataset = await repo.get(DEMO_SYMBOL, DEMO_TIMEFRAME)
        if dataset is not None:
            dataset.status = DatasetStatus.PENDING
            dataset.candle_count = 0
            dataset.start_at = None
            dataset.end_at = None
            dataset.message = "demo data removed"
            await repo.upsert(dataset)
    print(f"Removed demo data for {DEMO_SYMBOL} {DEMO_TIMEFRAME}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--remove", action="store_true", help="delete the demo dataset")
    args = parser.parse_args()
    container = Container(Settings())
    try:
        await (remove(container) if args.remove else seed(container))
    finally:
        await container.aclose()


if __name__ == "__main__":
    asyncio.run(main())
