"""Parquet-backed candle store.

Layout: ``{root}/{symbol}/{timeframe}.parquet``, one file per series, indexed
by UTC candle-open time. Writes are atomic (tmp file + rename) and appends
deduplicate on the index so re-syncing the same range is harmless.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from quantlab.application.ports import CandleStore, Coverage
from quantlab.domain.market import Symbol, Timeframe


class ParquetCandleStore(CandleStore):
    """Stores each (symbol, timeframe) series as a single Parquet file."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def path_for(self, symbol: Symbol, timeframe: Timeframe) -> Path:
        return self._root / symbol.value / f"{timeframe.value}.parquet"

    def coverage(self, symbol: Symbol, timeframe: Timeframe) -> Coverage | None:
        path = self.path_for(symbol, timeframe)
        if not path.exists():
            return None
        index = pd.read_parquet(path, columns=["close"]).index
        if len(index) == 0:
            return None
        return Coverage(
            start=index.min().to_pydatetime(),
            end=index.max().to_pydatetime(),
            candle_count=len(index),
        )

    def append(self, symbol: Symbol, timeframe: Timeframe, candles: pd.DataFrame) -> Coverage:
        path = self.path_for(symbol, timeframe)
        merged = candles
        if path.exists():
            existing = pd.read_parquet(path)
            merged = pd.concat([existing, candles])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        self._write_atomic(path, merged)
        return Coverage(
            start=merged.index.min().to_pydatetime(),
            end=merged.index.max().to_pydatetime(),
            candle_count=len(merged),
        )

    def load(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        frame = pd.read_parquet(self.path_for(symbol, timeframe))
        if start is not None:
            frame = frame[frame.index >= start]
        if end is not None:
            frame = frame[frame.index <= end]
        return frame

    @staticmethod
    def _write_atomic(path: Path, frame: pd.DataFrame) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".parquet.tmp")
        frame.to_parquet(tmp)
        tmp.replace(path)
