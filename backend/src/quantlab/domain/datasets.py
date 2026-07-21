"""Dataset entity: the catalog record describing one locally stored candle series."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from quantlab.domain.events import DomainEvent
from quantlab.domain.market import Symbol, Timeframe


class DatasetStatus(StrEnum):
    PENDING = "pending"
    SYNCING = "syncing"
    READY = "ready"
    ERROR = "error"


@dataclass
class Dataset:
    """Metadata about one (symbol, timeframe) candle series stored in Parquet."""

    symbol: Symbol
    timeframe: Timeframe
    status: DatasetStatus = DatasetStatus.PENDING
    candle_count: int = 0
    start_at: datetime | None = None
    end_at: datetime | None = None
    path: str | None = None
    source: str = ""
    message: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    updated_at: datetime | None = None


@dataclass(frozen=True, kw_only=True)
class DatasetSyncCompleted(DomainEvent):
    """A dataset finished synchronizing successfully."""

    symbol: Symbol
    timeframe: Timeframe
    new_candles: int
    total_candles: int


@dataclass(frozen=True, kw_only=True)
class DatasetSyncFailed(DomainEvent):
    """A dataset synchronization attempt failed."""

    symbol: Symbol
    timeframe: Timeframe
    error: str
