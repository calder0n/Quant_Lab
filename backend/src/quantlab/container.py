"""Composition root (dependency injection container).

One ``Container`` instance is created per process (API, worker, CLI) and owns
the lifecycle of every shared resource. Resources are built lazily on first
access and torn down in :meth:`aclose`. Nothing in QuantLab is a module-level
global; anything that needs a dependency receives it from here.
"""

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, time
from typing import TYPE_CHECKING

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from quantlab.application.event_bus import EventBus, InMemoryEventBus
from quantlab.application.ports import (
    AuthRepository,
    AutoTraderRepository,
    BacktestEngine,
    BrokerSettingsRepository,
    CandleStore,
    DatasetRepository,
    ExecutionBroker,
    MarketDataProvider,
    MlModelRepository,
    OptimizationRepository,
    TradeHistoryRepository,
    TradingStateRepository,
    ValidationRepository,
)
from quantlab.application.services.auth import AuthService
from quantlab.application.services.autotrader import AutoTraderService
from quantlab.application.services.backtesting import BacktestService
from quantlab.application.services.data_ingestion import DataIngestionService
from quantlab.application.services.ml import MlService
from quantlab.application.services.optimization import OptimizationService
from quantlab.application.services.trading import TradingService
from quantlab.application.services.validation import ValidationService
from quantlab.config import Settings
from quantlab.domain.broker import OANDA, BrokerCredentials
from quantlab.infrastructure.brokers.oanda.client import OandaClient
from quantlab.infrastructure.brokers.oanda.market_data import OandaMarketDataProvider
from quantlab.infrastructure.cache.redis import create_redis
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from quantlab.infrastructure.db.repositories.auth import (
    SqlAlchemyAuthRepository,
    SqlAlchemyTradingStateRepository,
)
from quantlab.infrastructure.db.repositories.autotrader import SqlAlchemyAutoTraderRepository
from quantlab.infrastructure.db.repositories.broker_settings import (
    SqlAlchemyBrokerSettingsRepository,
)
from quantlab.infrastructure.db.repositories.dataset import SqlAlchemyDatasetRepository
from quantlab.infrastructure.db.repositories.ml import SqlAlchemyMlModelRepository
from quantlab.infrastructure.db.repositories.optimization import (
    SqlAlchemyOptimizationRepository,
)
from quantlab.infrastructure.db.repositories.validation import SqlAlchemyValidationRepository
from quantlab.infrastructure.db.session import create_engine, create_session_factory
from quantlab.infrastructure.security import fernet_from_secret
from quantlab.strategies.registry import StrategyRegistry

if TYPE_CHECKING:
    from arq.connections import ArqRedis

logger = logging.getLogger(__name__)


class Container:
    """Owns and wires the shared resources of a QuantLab process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._redis: Redis | None = None
        self._event_bus: EventBus | None = None
        self._market_data_provider: OandaMarketDataProvider | None = None
        self._provider_fingerprint: tuple[str, str] | None = None
        self._candle_store: CandleStore | None = None
        self._data_ingestion: DataIngestionService | None = None
        self._strategy_registry: StrategyRegistry | None = None
        self._backtest_engine: BacktestEngine | None = None
        self._backtest_service: BacktestService | None = None
        self._optimization_service: OptimizationService | None = None
        self._validation_service: ValidationService | None = None
        self._ml_service: MlService | None = None
        self._auth_service: AuthService | None = None
        self._trading_service: TradingService | None = None
        self._auto_trader_service: AutoTraderService | None = None
        self._arq_pool: ArqRedis | None = None

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

    @asynccontextmanager
    async def broker_settings_repository(self) -> AsyncIterator[BrokerSettingsRepository]:
        """Open a transactional scope over the broker credentials store."""
        fernet = fernet_from_secret(self._settings.secret_key)
        async with self.session_factory() as session, session.begin():
            yield SqlAlchemyBrokerSettingsRepository(session, fernet=fernet)

    async def oanda_credentials(self) -> BrokerCredentials:
        """Resolve OANDA credentials: portal-configured (DB) wins over environment."""
        stored: BrokerCredentials | None = None
        try:
            async with self.broker_settings_repository() as repo:
                stored = await repo.get(OANDA)
        except Exception:
            logger.warning("Could not read broker settings from database; using environment")
        if stored is not None and stored.configured:
            return stored
        return BrokerCredentials(
            api_token=self._settings.oanda_api_token,
            account_id=self._settings.oanda_account_id,
            environment=self._settings.oanda_environment,
        )

    async def market_data_provider(self) -> MarketDataProvider:
        """OANDA adapter built from the current credentials; rebuilt when they change."""
        credentials = await self.oanda_credentials()
        fingerprint = (credentials.api_token, credentials.environment)
        if self._market_data_provider is None or self._provider_fingerprint != fingerprint:
            if self._market_data_provider is not None:
                await self._market_data_provider.aclose()
            client = OandaClient(
                api_token=credentials.api_token, environment=credentials.environment
            )
            self._market_data_provider = OandaMarketDataProvider(client)
            self._provider_fingerprint = fingerprint
            self._data_ingestion = None  # rebuilt with the new provider
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

    async def data_ingestion(self) -> DataIngestionService:
        """Ingestion service bound to the currently configured credentials."""
        provider = await self.market_data_provider()
        if self._data_ingestion is None:
            history_start = datetime.combine(self._settings.history_start, time.min, tzinfo=UTC)
            self._data_ingestion = DataIngestionService(
                provider=provider,
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

    @asynccontextmanager
    async def optimization_repository(self) -> AsyncIterator[OptimizationRepository]:
        """Open a transactional scope over the optimization store."""
        async with self.session_factory() as session, session.begin():
            yield SqlAlchemyOptimizationRepository(session)

    @property
    def optimization_service(self) -> OptimizationService:
        if self._optimization_service is None:
            # Imported lazily: optuna is heavy and only workers run studies.
            from quantlab.infrastructure.optimizers.optuna_optimizer import OptunaOptimizer
            from quantlab.infrastructure.optimizers.random_search import RandomSearchOptimizer

            self._optimization_service = OptimizationService(
                store=self.candle_store,
                registry=self.strategy_registry,
                engine=self.backtest_engine,
                repositories=self.optimization_repository,
                event_bus=self.event_bus,
                optimizers={"optuna": OptunaOptimizer, "random": RandomSearchOptimizer},
            )
        return self._optimization_service

    @asynccontextmanager
    async def validation_repository(self) -> AsyncIterator[ValidationRepository]:
        """Open a transactional scope over the validation store."""
        async with self.session_factory() as session, session.begin():
            yield SqlAlchemyValidationRepository(session)

    @property
    def validation_service(self) -> ValidationService:
        if self._validation_service is None:
            from quantlab.infrastructure.optimizers.optuna_optimizer import OptunaOptimizer
            from quantlab.infrastructure.optimizers.random_search import RandomSearchOptimizer

            self._validation_service = ValidationService(
                store=self.candle_store,
                registry=self.strategy_registry,
                engine=self.backtest_engine,
                repositories=self.validation_repository,
                event_bus=self.event_bus,
                optimizers={"optuna": OptunaOptimizer, "random": RandomSearchOptimizer},
            )
        return self._validation_service

    @asynccontextmanager
    async def ml_model_repository(self) -> AsyncIterator[MlModelRepository]:
        """Open a transactional scope over the model registry."""
        async with self.session_factory() as session, session.begin():
            yield SqlAlchemyMlModelRepository(session)

    @property
    def ml_service(self) -> MlService:
        if self._ml_service is None:
            self._ml_service = MlService(
                store=self.candle_store,
                repositories=self.ml_model_repository,
                event_bus=self.event_bus,
                artifacts_dir=self._settings.data_dir / "models",
            )
        return self._ml_service

    @asynccontextmanager
    async def auth_repository(self) -> AsyncIterator[AuthRepository]:
        """Open a transactional scope over users and API keys."""
        async with self.session_factory() as session, session.begin():
            yield SqlAlchemyAuthRepository(session)

    @property
    def auth_service(self) -> AuthService:
        if self._auth_service is None:
            self._auth_service = AuthService(
                repositories=self.auth_repository,
                secret_key=self._settings.secret_key,
                token_ttl_minutes=self._settings.access_token_ttl_minutes,
            )
        return self._auth_service

    @asynccontextmanager
    async def trading_state_repository(self) -> AsyncIterator[TradingStateRepository]:
        """Open a transactional scope over the trading kill switch."""
        async with self.session_factory() as session, session.begin():
            yield SqlAlchemyTradingStateRepository(session)

    async def execution_broker(self) -> ExecutionBroker:
        """OANDA execution adapter for the currently configured account."""
        from quantlab.infrastructure.brokers.oanda.execution import OandaExecutionBroker

        credentials = await self.oanda_credentials()
        if not credentials.configured or not credentials.account_id:
            raise ValueError("OANDA credentials with an account id are required for trading.")
        client = OandaClient(api_token=credentials.api_token, environment=credentials.environment)
        return OandaExecutionBroker(client, credentials.account_id)

    @asynccontextmanager
    async def trade_history_repository(self) -> AsyncIterator[TradeHistoryRepository]:
        """Open a transactional scope over the executed-order history."""
        from quantlab.infrastructure.db.repositories.trade_history import (
            SqlAlchemyTradeHistoryRepository,
        )

        async with self.session_factory() as session, session.begin():
            yield SqlAlchemyTradeHistoryRepository(session)

    @property
    def trading_service(self) -> TradingService:
        if self._trading_service is None:
            self._trading_service = TradingService(
                states=self.trading_state_repository,
                broker_factory=self.execution_broker,
                credentials_resolver=self.oanda_credentials,
                registry=self.strategy_registry,
                market_data=self.market_data_provider,
                event_bus=self.event_bus,
                trades=self.trade_history_repository,
            )
        return self._trading_service

    @asynccontextmanager
    async def auto_trader_repository(self) -> AsyncIterator[AutoTraderRepository]:
        """Open a transactional scope over the auto-trading assignments."""
        async with self.session_factory() as session, session.begin():
            yield SqlAlchemyAutoTraderRepository(session)

    @property
    def auto_trader_service(self) -> AutoTraderService:
        if self._auto_trader_service is None:
            self._auto_trader_service = AutoTraderService(
                repositories=self.auto_trader_repository,
                states=self.trading_state_repository,
                trading_service=self.trading_service,
                registry=self.strategy_registry,
                market_data=self.market_data_provider,
            )
        return self._auto_trader_service

    async def enqueue_training(self, model_id: uuid.UUID) -> None:
        """Queue one model training for execution by a worker."""
        from quantlab.interfaces.worker.settings import QUEUE_NAME, TRAINING_JOB

        pool = await self.job_queue()
        await pool.enqueue_job(TRAINING_JOB, str(model_id), _queue_name=QUEUE_NAME)

    async def enqueue_validation(self, run_id: uuid.UUID) -> None:
        """Queue one validation run for execution by a worker."""
        from quantlab.interfaces.worker.settings import QUEUE_NAME, VALIDATION_JOB

        pool = await self.job_queue()
        await pool.enqueue_job(VALIDATION_JOB, str(run_id), _queue_name=QUEUE_NAME)

    async def job_queue(self) -> "ArqRedis":
        """Redis-backed job queue (arq) used to dispatch work to workers."""
        if self._arq_pool is None:
            from arq import create_pool

            from quantlab.interfaces.worker.settings import redis_settings

            self._arq_pool = await create_pool(redis_settings(self._settings))
        return self._arq_pool

    async def enqueue_optimization(self, study_id: uuid.UUID) -> None:
        """Queue one study for execution by a worker."""
        from quantlab.interfaces.worker.settings import OPTIMIZATION_JOB, QUEUE_NAME

        pool = await self.job_queue()
        await pool.enqueue_job(OPTIMIZATION_JOB, str(study_id), _queue_name=QUEUE_NAME)

    async def aclose(self) -> None:
        """Release every resource that was actually created."""
        if self._arq_pool is not None:
            await self._arq_pool.aclose()
            self._arq_pool = None
        if self._market_data_provider is not None:
            await self._market_data_provider.aclose()
            self._market_data_provider = None
            self._provider_fingerprint = None
            self._data_ingestion = None
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
