"""Tests for the Parquet candle store."""

from pathlib import Path

from quantlab.domain.market import Symbol, Timeframe
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from tests.factories import make_candles, utc


def make_store(tmp_path: Path) -> ParquetCandleStore:
    return ParquetCandleStore(tmp_path / "candles")


def test_coverage_is_none_when_nothing_stored(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    assert store.coverage(Symbol.EURUSD, Timeframe.H1) is None


def test_append_writes_and_reports_coverage(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    coverage = store.append(Symbol.EURUSD, Timeframe.H1, make_candles(utc(2024, 1, 1), 24))
    assert coverage.candle_count == 24
    assert coverage.start == utc(2024, 1, 1)
    assert coverage.end == utc(2024, 1, 1, 23)
    assert store.path_for(Symbol.EURUSD, Timeframe.H1).exists()
    assert store.coverage(Symbol.EURUSD, Timeframe.H1) == coverage


def test_append_deduplicates_and_sorts(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    later = make_candles(utc(2024, 1, 1, 12), 12)
    earlier = make_candles(utc(2024, 1, 1), 14)  # overlaps hours 12-13
    store.append(Symbol.EURUSD, Timeframe.H1, later)
    coverage = store.append(Symbol.EURUSD, Timeframe.H1, earlier)
    assert coverage.candle_count == 24  # not 26: overlap deduplicated
    frame = store.load(Symbol.EURUSD, Timeframe.H1)
    assert frame.index.is_monotonic_increasing
    assert not frame.index.duplicated().any()


def test_load_slices_by_range(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.append(Symbol.GBPUSD, Timeframe.H1, make_candles(utc(2024, 1, 1), 24))
    frame = store.load(
        Symbol.GBPUSD, Timeframe.H1, start=utc(2024, 1, 1, 5), end=utc(2024, 1, 1, 10)
    )
    assert len(frame) == 6
    assert frame.index[0] == utc(2024, 1, 1, 5)
    assert frame.index[-1] == utc(2024, 1, 1, 10)


def test_series_are_isolated_per_symbol_and_timeframe(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.append(Symbol.EURUSD, Timeframe.H1, make_candles(utc(2024, 1, 1), 3))
    store.append(Symbol.EURUSD, Timeframe.D1, make_candles(utc(2024, 1, 1), 2))
    assert store.coverage(Symbol.EURUSD, Timeframe.H1).candle_count == 3  # type: ignore[union-attr]
    assert store.coverage(Symbol.EURUSD, Timeframe.D1).candle_count == 2  # type: ignore[union-attr]
    assert store.coverage(Symbol.GBPUSD, Timeframe.H1) is None
