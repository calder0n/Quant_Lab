"""Factory helpers for the async SQLAlchemy engine and session maker.

These are plain factories — no module-level state. The composition root
(`quantlab.container.Container`) owns the lifecycle of the objects they create.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from quantlab.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Build the application's async engine from configuration."""
    return create_async_engine(
        settings.postgres_dsn,
        echo=settings.debug,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build the session factory bound to ``engine``."""
    return async_sessionmaker(engine, expire_on_commit=False)
