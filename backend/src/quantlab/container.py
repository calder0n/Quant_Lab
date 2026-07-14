"""Composition root (dependency injection container).

One ``Container`` instance is created per process (API, worker, CLI) and owns
the lifecycle of every shared resource. Resources are built lazily on first
access and torn down in :meth:`aclose`. Nothing in QuantLab is a module-level
global; anything that needs a dependency receives it from here.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from quantlab.application.event_bus import EventBus, InMemoryEventBus
from quantlab.application.ports import (
    BacktestEngine,
    CandleStore,
    DatasetRepository,
    MarketDataProvider,
)
from quantlab.application.services.backtesting import BacktestService
from quantlab.application.services.data_ingestion import DataIngestionService
from quantlab.config import Settings
from quantlab.infrastructure.brokers.oanda.client import OandaClient
from quantlab.infrastructure.brokers.oanda.market_data import OandaMarketDataProvider
from quantlab.infrastructure.cache.redis import create_redis
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from quantlab.infrastructure.db.repositories.dataset import SqlAlchemyDatasetRepository
from quantlab.infrastructure.db.session import create_engine, create_session_factory
from quantlab.strategies.registry import StrategyRegistry


class Container:
    """Owns and wires the shared resources of a QuantLab process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._redis: Redis | None = None
        self._event_bus: EventBus | None = None
        self._market_data_provider: OandaMarketDataProvider | None = None
        self._candle_store: CandleStore | None = None
        self._data_ingestion: DataIngestionService | None = None
        self._strategy_registry: StrategyRegistry | None = None
        self._backtest_engine: BacktestEngine | None = None
        self._backtest_service: BacktestService | None = None

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_engine(self._settings)
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            self._session_factory = create_session_factory(self.engine)
        return self._session_factory

    @property
    def redis(self) -> Redis:
        if self._redis is None:
            self._redis = create_redis(self._settings)
        return self._redis

    @property
    def event_bus(self) -> EventBus:
        if self._event_bus is None:
            self._event_bus = InMemoryEventBus()
        return self._event_bus

    @property
    def market_data_provider(self) -> MarketDataProvider:
        if self._market_data_provider is None:
            client = OandaClient(
                api_token=self._settings.oanda_api_token,
                environment=self._settings.oanda_environment,
            )
            self._market_data_provider = OandaMarketDataProvider(client)
        return self._market_data_provider

    @property
    def candle_store(self) -> CandleStore:
        if self._candle_store is None:
            self._candle_store = ParquetCandleStore(self._settings.data_dir / "candles")
        return self._candle_store

    @asynccontextmanager
    async def dataset_repository(self) -> AsyncIterator[DatasetRepository]:
        """Open a transactional, request-independent repository scope."""
        async with self.session_factory() as session, session.begin():
            yield SqlAlchemyDatasetRepository(session)

    @property
    def data_ingestion(self) -> DataIngestionService:
        if self._data_ingestion is None:
            history_start = datetime.combine(self._settings.history_start, time.min, tzinfo=UTC)
            self._data_ingestion = DataIngestionService(
                provider=self.market_data_provider,
                store=self.candle_store,
                repositories=self.dataset_repository,
                event_bus=self.event_bus,
                history_start=history_start,
            )
        return self._data_ingestion

    @property
    def strategy_registry(self) -> StrategyRegistry:
        if self._strategy_registry is None:
            self._strategy_registry = StrategyRegistry().discover()
        return self._strategy_registry

    @property
    def backtest_engine(self) -> BacktestEngine:
        if self._backtest_engine is None:
            # Imported lazily: vectorbt/numba are heavy and not every process needs them.
            from quantlab.infrastructure.backtesting.vectorbt_engine import (
                VectorbtBacktestEngine,
            )

            self._backtest_engine = VectorbtBacktestEngine()
        return self._backtest_engine

    @property
    def backtest_service(self) -> BacktestService:
        if self._backtest_service is None:
            self._backtest_service = BacktestService(
                store=self.candle_store,
                registry=self.strategy_registry,
                engine=self.backtest_engine,
            )
        return self._backtest_service

    async def aclose(self) -> None:
        """Release every resource that was actually created."""
        if self._market_data_provider is not None:
            await self._market_data_provider.aclose()
            self._market_data_provider = None
            self._data_ingestion = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
