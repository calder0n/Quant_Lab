"""Composition root (dependency injection container).

One ``Container`` instance is created per process (API, worker, CLI) and owns
the lifecycle of every shared resource. Resources are built lazily on first
access and torn down in :meth:`aclose`. Nothing in QuantLab is a module-level
global; anything that needs a dependency receives it from here.
"""

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from quantlab.application.event_bus import EventBus, InMemoryEventBus
from quantlab.config import Settings
from quantlab.infrastructure.cache.redis import create_redis
from quantlab.infrastructure.db.session import create_engine, create_session_factory


class Container:
    """Owns and wires the shared resources of a QuantLab process."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._redis: Redis | None = None
        self._event_bus: EventBus | None = None

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

    async def aclose(self) -> None:
        """Release every resource that was actually created."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
