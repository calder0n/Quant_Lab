"""Tests for the SQLAlchemy broker settings repository (in-memory SQLite)."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from quantlab.domain.broker import OANDA, BrokerCredentials
from quantlab.infrastructure.db.base import Base
from quantlab.infrastructure.db.repositories.broker_settings import (
    SqlAlchemyBrokerSettingsRepository,
)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


async def test_get_returns_none_when_unconfigured(session: AsyncSession) -> None:
    repo = SqlAlchemyBrokerSettingsRepository(session)
    assert await repo.get(OANDA) is None


async def test_upsert_inserts_then_updates(session: AsyncSession) -> None:
    repo = SqlAlchemyBrokerSettingsRepository(session)
    saved = await repo.upsert(
        BrokerCredentials(api_token="secret-token-123", account_id="001-1", environment="practice")
    )
    assert saved.api_token == "secret-token-123"
    assert saved.updated_at is not None

    saved.environment = "live"
    saved.account_id = "001-2"
    updated = await repo.upsert(saved)
    assert updated.environment == "live"
    fetched = await repo.get(OANDA)
    assert fetched is not None
    assert fetched.account_id == "001-2"
    assert fetched.api_token == "secret-token-123"


async def test_delete_removes_the_row(session: AsyncSession) -> None:
    repo = SqlAlchemyBrokerSettingsRepository(session)
    await repo.upsert(BrokerCredentials(api_token="secret-token-123"))
    await repo.delete(OANDA)
    assert await repo.get(OANDA) is None


def test_token_preview_masks_the_token() -> None:
    assert BrokerCredentials(api_token="abcdef123456").token_preview == "····3456"
    assert BrokerCredentials(api_token="short").token_preview == "····"
    assert BrokerCredentials().token_preview is None
    assert not BrokerCredentials().configured
