"""SQLAlchemy implementation of the ``DatasetRepository`` port."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantlab.application.ports import DatasetRepository
from quantlab.domain.datasets import Dataset, DatasetStatus
from quantlab.domain.market import Symbol, Timeframe
from quantlab.infrastructure.db.models.dataset import DatasetRecord


def _to_entity(record: DatasetRecord) -> Dataset:
    return Dataset(
        id=record.id,
        symbol=Symbol(record.symbol),
        timeframe=Timeframe(record.timeframe),
        status=DatasetStatus(record.status),
        candle_count=record.candle_count,
        start_at=record.start_at,
        end_at=record.end_at,
        path=record.path,
        source=record.source,
        message=record.message,
        updated_at=record.updated_at,
    )


class SqlAlchemyDatasetRepository(DatasetRepository):
    """Dataset catalog persisted in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, symbol: Symbol, timeframe: Timeframe) -> Dataset | None:
        record = await self._find(symbol, timeframe)
        return _to_entity(record) if record is not None else None

    async def list_all(self) -> list[Dataset]:
        result = await self._session.execute(
            select(DatasetRecord).order_by(DatasetRecord.symbol, DatasetRecord.timeframe)
        )
        return [_to_entity(record) for record in result.scalars()]

    async def upsert(self, dataset: Dataset) -> Dataset:
        record = await self._find(dataset.symbol, dataset.timeframe)
        if record is None:
            record = DatasetRecord(
                id=dataset.id,
                symbol=dataset.symbol.value,
                timeframe=dataset.timeframe.value,
            )
            self._session.add(record)
        record.status = dataset.status.value
        record.candle_count = dataset.candle_count
        record.start_at = dataset.start_at
        record.end_at = dataset.end_at
        record.path = dataset.path
        record.source = dataset.source
        record.message = dataset.message
        await self._session.flush()
        await self._session.refresh(record)
        return _to_entity(record)

    async def _find(self, symbol: Symbol, timeframe: Timeframe) -> DatasetRecord | None:
        result = await self._session.execute(
            select(DatasetRecord).where(
                DatasetRecord.symbol == symbol.value,
                DatasetRecord.timeframe == timeframe.value,
            )
        )
        return result.scalar_one_or_none()
