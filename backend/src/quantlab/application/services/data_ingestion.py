"""Idempotent historical data ingestion.

The Parquet store is the source of truth for *which candles already exist*;
this service only requests the missing head/tail ranges from the market data
provider, so historical data is downloaded exactly once. The SQL catalog is a
queryable projection of that state.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime, timedelta

from quantlab.application.event_bus import EventBus
from quantlab.application.ports import (
    CandleStore,
    Coverage,
    DatasetRepository,
    MarketDataProvider,
)
from quantlab.domain.datasets import (
    Dataset,
    DatasetStatus,
    DatasetSyncCompleted,
    DatasetSyncFailed,
)
from quantlab.domain.market import Symbol, Timeframe

logger = logging.getLogger(__name__)

DatasetRepositoryFactory = Callable[[], AbstractAsyncContextManager[DatasetRepository]]


def missing_ranges(
    coverage: Coverage | None,
    history_start: datetime,
    end: datetime,
    step: timedelta,
) -> list[tuple[datetime, datetime]]:
    """Compute the time ranges not yet stored locally.

    Returns up to two ranges: a head backfill (when ``history_start`` was moved
    earlier than the stored data) and a tail update (new candles since the last
    sync). An empty list means the store already covers everything.
    """
    if coverage is None:
        return [(history_start, end)]
    ranges: list[tuple[datetime, datetime]] = []
    if history_start < coverage.start - step:
        ranges.append((history_start, coverage.start - step))
    if coverage.end + step <= end:
        ranges.append((coverage.end + step, end))
    return ranges


class DataIngestionService:
    """Downloads and catalogs historical candles, fetching only what is missing."""

    def __init__(
        self,
        provider: MarketDataProvider,
        store: CandleStore,
        repositories: DatasetRepositoryFactory,
        event_bus: EventBus,
        history_start: datetime,
    ) -> None:
        self._provider = provider
        self._store = store
        self._repositories = repositories
        self._event_bus = event_bus
        self._history_start = history_start

    async def sync(
        self, symbol: Symbol, timeframe: Timeframe, end: datetime | None = None
    ) -> Dataset:
        """Bring one series up to date. Never raises: failures land in the catalog."""
        end_at = end if end is not None else datetime.now(UTC)
        dataset = await self._transition(symbol, timeframe, DatasetStatus.SYNCING)
        try:
            new_candles = await self._download_missing(symbol, timeframe, end_at)
        except Exception as exc:
            logger.exception("Sync failed for %s %s", symbol, timeframe)
            error_message = f"{type(exc).__name__}: {exc}"
            dataset.status = DatasetStatus.ERROR
            dataset.message = error_message
            dataset = await self._save(dataset)
            await self._event_bus.publish(
                DatasetSyncFailed(symbol=symbol, timeframe=timeframe, error=error_message)
            )
            return dataset

        coverage = self._store.coverage(symbol, timeframe)
        dataset.status = DatasetStatus.READY
        dataset.message = None
        dataset.source = self._provider.name
        dataset.path = str(self._store.path_for(symbol, timeframe))
        if coverage is not None:
            dataset.candle_count = coverage.candle_count
            dataset.start_at = coverage.start
            dataset.end_at = coverage.end
        dataset = await self._save(dataset)
        await self._event_bus.publish(
            DatasetSyncCompleted(
                symbol=symbol,
                timeframe=timeframe,
                new_candles=new_candles,
                total_candles=dataset.candle_count,
            )
        )
        return dataset

    async def sync_all(
        self,
        symbols: list[Symbol] | None = None,
        timeframes: list[Timeframe] | None = None,
    ) -> list[Dataset]:
        """Sequentially sync every requested (symbol, timeframe) pair."""
        results = []
        for symbol in symbols or list(Symbol):
            for timeframe in timeframes or list(Timeframe):
                results.append(await self.sync(symbol, timeframe))
        return results

    async def _download_missing(self, symbol: Symbol, timeframe: Timeframe, end: datetime) -> int:
        coverage = self._store.coverage(symbol, timeframe)
        total = 0
        for range_start, range_end in missing_ranges(
            coverage, self._history_start, end, timeframe.delta
        ):
            candles = await self._provider.fetch_candles(symbol, timeframe, range_start, range_end)
            if not candles.empty:
                self._store.append(symbol, timeframe, candles)
                total += len(candles)
        return total

    async def _transition(
        self, symbol: Symbol, timeframe: Timeframe, status: DatasetStatus
    ) -> Dataset:
        async with self._repositories() as repo:
            dataset = await repo.get(symbol, timeframe) or Dataset(
                symbol=symbol, timeframe=timeframe, source=self._provider.name
            )
            dataset.status = status
            return await repo.upsert(dataset)

    async def _save(self, dataset: Dataset) -> Dataset:
        async with self._repositories() as repo:
            return await repo.upsert(dataset)
