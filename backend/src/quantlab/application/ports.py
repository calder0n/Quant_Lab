"""Application ports: interfaces the infrastructure layer must implement.

Application services depend only on these abstractions (Dependency Inversion);
concrete adapters (OANDA, Parquet, SQLAlchemy) are wired in by the container.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from quantlab.domain.backtest import BacktestResult, CostModel, OrderPlan
from quantlab.domain.datasets import Dataset
from quantlab.domain.market import Symbol, Timeframe


@dataclass(frozen=True)
class Coverage:
    """Actual extent of the candles stored locally for one series."""

    start: datetime
    end: datetime
    candle_count: int


class MarketDataProvider(ABC):
    """Source of historical candles (a broker or data vendor adapter).

    Implementations return a DataFrame indexed by UTC candle-open time with
    the columns in :data:`quantlab.domain.market.CANDLE_COLUMNS`. Only
    completed candles are returned.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Identifier of the data source (e.g. ``"oanda"``)."""

    @abstractmethod
    async def fetch_candles(
        self, symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime
    ) -> pd.DataFrame:
        """Fetch candles with open time in ``[start, end]``."""


class CandleStore(ABC):
    """Local persistent storage for candle series."""

    @abstractmethod
    def path_for(self, symbol: Symbol, timeframe: Timeframe) -> Path:
        """Filesystem location of the series."""

    @abstractmethod
    def coverage(self, symbol: Symbol, timeframe: Timeframe) -> Coverage | None:
        """Extent of stored data, or ``None`` when nothing is stored yet."""

    @abstractmethod
    def append(self, symbol: Symbol, timeframe: Timeframe, candles: pd.DataFrame) -> Coverage:
        """Merge ``candles`` into the series (dedup + sort) and return new coverage."""

    @abstractmethod
    def load(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> pd.DataFrame:
        """Read the series, optionally sliced to ``[start, end]``."""


class BacktestEngine(ABC):
    """Executes a signal frame over candle data and computes the metric set.

    Implementations must delay execution by one bar relative to the signal
    (signals are computed on closed candles) so no engine can look ahead.
    """

    @abstractmethod
    def run(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        orders: OrderPlan,
        costs: CostModel,
        timeframe: Timeframe,
    ) -> BacktestResult: ...


class DatasetRepository(ABC):
    """Persistence port for the dataset catalog (metadata in PostgreSQL)."""

    @abstractmethod
    async def get(self, symbol: Symbol, timeframe: Timeframe) -> Dataset | None: ...

    @abstractmethod
    async def list_all(self) -> list[Dataset]: ...

    @abstractmethod
    async def upsert(self, dataset: Dataset) -> Dataset:
        """Insert or update the catalog entry identified by (symbol, timeframe)."""
