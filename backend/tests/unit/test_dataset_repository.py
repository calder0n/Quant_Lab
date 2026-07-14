"""Tests for the SQLAlchemy dataset repository (against in-memory SQLite)."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from quantlab.domain.datasets import Dataset, DatasetStatus
from quantlab.domain.market import Symbol, Timeframe
from quantlab.infrastructure.db.base import Base
from quantlab.infrastructure.db.repositories.dataset import SqlAlchemyDatasetRepository
from tests.factories import utc


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


async def test_get_returns_none_for_unknown_series(session: AsyncSession) -> None:
    repo = SqlAlchemyDatasetRepository(session)
    assert await repo.get(Symbol.EURUSD, Timeframe.H1) is None


async def test_upsert_inserts_then_updates(session: AsyncSession) -> None:
    repo = SqlAlchemyDatasetRepository(session)
    dataset = Dataset(symbol=Symbol.EURUSD, timeframe=Timeframe.H1, source="oanda")
    saved = await repo.upsert(dataset)
    assert saved.id == dataset.id
    assert saved.status == DatasetStatus.PENDING

    saved.status = DatasetStatus.READY
    saved.candle_count = 1000
    saved.start_at = utc(2024, 1, 1)
    saved.end_at = utc(2024, 6, 1)
    updated = await repo.upsert(saved)
    assert updated.id == dataset.id  # same row, not a duplicate
    assert updated.status == DatasetStatus.READY
    assert updated.candle_count == 1000

    fetched = await repo.get(Symbol.EURUSD, Timeframe.H1)
    assert fetched is not None
    assert fetched.candle_count == 1000


async def test_list_all_is_ordered_by_symbol_and_timeframe(session: AsyncSession) -> None:
    repo = SqlAlchemyDatasetRepository(session)
    await repo.upsert(Dataset(symbol=Symbol.USDJPY, timeframe=Timeframe.M5))
    await repo.upsert(Dataset(symbol=Symbol.AUDUSD, timeframe=Timeframe.H1))
    await repo.upsert(Dataset(symbol=Symbol.AUDUSD, timeframe=Timeframe.D1))
    listed = await repo.list_all()
    assert [(d.symbol, d.timeframe) for d in listed] == [
        (Symbol.AUDUSD, Timeframe.D1),
        (Symbol.AUDUSD, Timeframe.H1),
        (Symbol.USDJPY, Timeframe.M5),
    ]
