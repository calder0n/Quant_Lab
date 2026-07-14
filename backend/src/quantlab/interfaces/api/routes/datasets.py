"""Dataset catalog endpoints: list local data and trigger idempotent syncs."""

import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel

from quantlab.domain.datasets import Dataset, DatasetStatus
from quantlab.domain.market import Symbol, Timeframe
from quantlab.interfaces.api.deps import ContainerDep

router = APIRouter(prefix="/datasets", tags=["datasets"])


class DatasetOut(BaseModel):
    id: uuid.UUID
    symbol: Symbol
    timeframe: Timeframe
    status: DatasetStatus
    candle_count: int
    start_at: datetime | None
    end_at: datetime | None
    path: str | None
    source: str
    message: str | None
    updated_at: datetime | None

    @classmethod
    def from_entity(cls, dataset: Dataset) -> "DatasetOut":
        return cls(
            id=dataset.id,
            symbol=dataset.symbol,
            timeframe=dataset.timeframe,
            status=dataset.status,
            candle_count=dataset.candle_count,
            start_at=dataset.start_at,
            end_at=dataset.end_at,
            path=dataset.path,
            source=dataset.source,
            message=dataset.message,
            updated_at=dataset.updated_at,
        )


class SyncRequest(BaseModel):
    symbols: list[Symbol] | None = None
    timeframes: list[Timeframe] | None = None


class SyncScheduled(BaseModel):
    symbols: list[Symbol]
    timeframes: list[Timeframe]
    pairs: int


@router.get("", response_model=list[DatasetOut])
async def list_datasets(container: ContainerDep) -> list[DatasetOut]:
    """Return every catalog entry."""
    async with container.dataset_repository() as repo:
        datasets = await repo.list_all()
    return [DatasetOut.from_entity(dataset) for dataset in datasets]


@router.post("/sync", response_model=SyncScheduled, status_code=status.HTTP_202_ACCEPTED)
async def sync_datasets(
    request: SyncRequest, background: BackgroundTasks, container: ContainerDep
) -> SyncScheduled:
    """Schedule an idempotent background download of the missing history."""
    if not container.settings.oanda_api_token:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="OANDA API token not configured (set QL_OANDA_API_TOKEN).",
        )
    symbols = request.symbols or list(Symbol)
    timeframes = request.timeframes or list(Timeframe)
    background.add_task(container.data_ingestion.sync_all, symbols, timeframes)
    return SyncScheduled(
        symbols=symbols, timeframes=timeframes, pairs=len(symbols) * len(timeframes)
    )
