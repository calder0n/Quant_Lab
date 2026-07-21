"""Tests for the idempotent data ingestion service."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

from quantlab.application.event_bus import InMemoryEventBus
from quantlab.application.ports import Coverage, DatasetRepository, MarketDataProvider
from quantlab.application.services.data_ingestion import DataIngestionService, missing_ranges
from quantlab.domain.datasets import (
    Dataset,
    DatasetStatus,
    DatasetSyncCompleted,
    DatasetSyncFailed,
)
from quantlab.domain.events import DomainEvent
from quantlab.domain.market import Symbol, Timeframe
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from tests.factories import make_candles, utc


class FakeProvider(MarketDataProvider):
    """Serves a fixed hourly series and records every requested range."""

    def __init__(self, series_start: datetime, total: int, fail: bool = False) -> None:
        self._candles = make_candles(series_start, total)
        self.requested: list[tuple[datetime, datetime]] = []
        self._fail = fail

    @property
    def name(self) -> str:
        return "fake"

    async def fetch_candles(
        self, symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime
    ) -> pd.DataFrame:
        if self._fail:
            raise ConnectionError("provider unavailable")
        self.requested.append((start, end))
        mask = (self._candles.index >= start) & (self._candles.index <= end)
        return self._candles[mask]


class InMemoryDatasetRepository(DatasetRepository):
    def __init__(self, storage: dict[tuple[Symbol, Timeframe], Dataset]) -> None:
        self._storage = storage

    async def get(self, symbol: Symbol, timeframe: Timeframe) -> Dataset | None:
        return self._storage.get((symbol, timeframe))

    async def list_all(self) -> list[Dataset]:
        return list(self._storage.values())

    async def upsert(self, dataset: Dataset) -> Dataset:
        self._storage[(dataset.symbol, dataset.timeframe)] = dataset
        return dataset


def build_service(
    tmp_path: Path, provider: MarketDataProvider, history_start: datetime
) -> tuple[DataIngestionService, dict[tuple[Symbol, Timeframe], Dataset], list[DomainEvent]]:
    storage: dict[tuple[Symbol, Timeframe], Dataset] = {}

    @asynccontextmanager
    async def repositories() -> AsyncIterator[DatasetRepository]:
        yield InMemoryDatasetRepository(storage)

    bus = InMemoryEventBus()
    events: list[DomainEvent] = []

    async def record(event: DomainEvent) -> None:
        events.append(event)

    bus.subscribe(DomainEvent, record)
    store = ParquetCandleStore(tmp_path / "candles")
    service = DataIngestionService(
        provider=provider,
        store=store,
        repositories=repositories,
        event_bus=bus,
        history_start=history_start,
    )
    return service, storage, events


def test_missing_ranges_full_when_no_coverage() -> None:
    ranges = missing_ranges(None, utc(2024, 1, 1), utc(2024, 1, 2), Timeframe.H1.delta)
    assert ranges == [(utc(2024, 1, 1), utc(2024, 1, 2))]


def test_missing_ranges_head_and_tail() -> None:
    coverage = Coverage(start=utc(2024, 1, 5), end=utc(2024, 1, 10), candle_count=1)
    ranges = missing_ranges(coverage, utc(2024, 1, 1), utc(2024, 1, 20), Timeframe.H1.delta)
    assert ranges == [
        (utc(2024, 1, 1), utc(2024, 1, 4, 23)),
        (utc(2024, 1, 10, 1), utc(2024, 1, 20)),
    ]


def test_missing_ranges_empty_when_fully_covered() -> None:
    coverage = Coverage(start=utc(2024, 1, 1), end=utc(2024, 1, 10), candle_count=1)
    assert missing_ranges(coverage, utc(2024, 1, 1), utc(2024, 1, 10), Timeframe.H1.delta) == []


async def test_initial_sync_downloads_everything(tmp_path: Path) -> None:
    provider = FakeProvider(utc(2024, 1, 1), total=48)
    service, _, events = build_service(tmp_path, provider, utc(2024, 1, 1))
    dataset = await service.sync(Symbol.EURUSD, Timeframe.H1, end=utc(2024, 1, 2, 23))
    assert dataset.status == DatasetStatus.READY
    assert dataset.candle_count == 48
    assert dataset.start_at == utc(2024, 1, 1)
    assert dataset.end_at == utc(2024, 1, 2, 23)
    assert dataset.source == "fake"
    assert dataset.path is not None
    completed = [e for e in events if isinstance(e, DatasetSyncCompleted)]
    assert len(completed) == 1
    assert completed[0].new_candles == 48


async def test_second_sync_fetches_only_the_missing_tail(tmp_path: Path) -> None:
    provider = FakeProvider(utc(2024, 1, 1), total=72)
    service, _, _ = build_service(tmp_path, provider, utc(2024, 1, 1))
    await service.sync(Symbol.EURUSD, Timeframe.H1, end=utc(2024, 1, 2, 23))
    provider.requested.clear()

    dataset = await service.sync(Symbol.EURUSD, Timeframe.H1, end=utc(2024, 1, 3, 23))
    assert provider.requested == [(utc(2024, 1, 3), utc(2024, 1, 3, 23))]
    assert dataset.candle_count == 72


async def test_sync_is_a_noop_when_already_covered(tmp_path: Path) -> None:
    provider = FakeProvider(utc(2024, 1, 1), total=24)
    service, _, _ = build_service(tmp_path, provider, utc(2024, 1, 1))
    await service.sync(Symbol.EURUSD, Timeframe.H1, end=utc(2024, 1, 1, 23))
    provider.requested.clear()

    dataset = await service.sync(Symbol.EURUSD, Timeframe.H1, end=utc(2024, 1, 1, 23))
    assert provider.requested == []  # nothing re-downloaded
    assert dataset.status == DatasetStatus.READY
    assert dataset.candle_count == 24


async def test_failed_sync_is_recorded_and_published(tmp_path: Path) -> None:
    provider = FakeProvider(utc(2024, 1, 1), total=0, fail=True)
    service, storage, events = build_service(tmp_path, provider, utc(2024, 1, 1))
    dataset = await service.sync(Symbol.EURUSD, Timeframe.H1, end=utc(2024, 1, 2))
    assert dataset.status == DatasetStatus.ERROR
    assert dataset.message is not None and "ConnectionError" in dataset.message
    failed = [e for e in events if isinstance(e, DatasetSyncFailed)]
    assert len(failed) == 1
    assert storage[(Symbol.EURUSD, Timeframe.H1)].status == DatasetStatus.ERROR


async def test_sync_all_covers_requested_pairs(tmp_path: Path) -> None:
    provider = FakeProvider(utc(2024, 1, 1), total=24)
    service, storage, _ = build_service(tmp_path, provider, utc(2024, 1, 1))
    results = await service.sync_all(
        symbols=[Symbol.EURUSD, Symbol.GBPUSD], timeframes=[Timeframe.H1]
    )
    assert len(results) == 2
    assert {(d.symbol, d.timeframe) for d in results} == set(storage)
