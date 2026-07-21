"""Tests for the SQLAlchemy validation repository (in-memory SQLite)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.optimization import StudyStatus
from quantlab.domain.validation import ValidationKind, ValidationRun
from quantlab.infrastructure.db.base import Base
from quantlab.infrastructure.db.repositories.validation import SqlAlchemyValidationRepository


@pytest.fixture
async def repo() -> AsyncIterator[SqlAlchemyValidationRepository]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield SqlAlchemyValidationRepository(session)
    await engine.dispose()


def make_run() -> ValidationRun:
    return ValidationRun(
        kind=ValidationKind.WALK_FORWARD,
        strategy_id="ema_cross",
        symbol=Symbol.EURUSD,
        timeframe=Timeframe.H1,
        params={"fast_period": 10},
        config={"n_folds": 3},
    )


async def test_create_and_get(repo: SqlAlchemyValidationRepository) -> None:
    run = await repo.create(make_run())
    fetched = await repo.get(run.id)
    assert fetched is not None
    assert fetched.kind == ValidationKind.WALK_FORWARD
    assert fetched.params == {"fast_period": 10}
    assert fetched.config == {"n_folds": 3}
    assert fetched.status == StudyStatus.PENDING
    assert fetched.created_at is not None


async def test_get_missing_returns_none(repo: SqlAlchemyValidationRepository) -> None:
    assert await repo.get(uuid.uuid4()) is None


async def test_update_stores_result(repo: SqlAlchemyValidationRepository) -> None:
    run = await repo.create(make_run())
    run.status = StudyStatus.COMPLETED
    run.result = {"kind": "walk_forward", "wf_efficiency": 0.8}
    updated = await repo.update(run)
    assert updated.status == StudyStatus.COMPLETED
    fetched = await repo.get(run.id)
    assert fetched is not None and fetched.result == {"kind": "walk_forward", "wf_efficiency": 0.8}


async def test_list_all(repo: SqlAlchemyValidationRepository) -> None:
    await repo.create(make_run())
    await repo.create(make_run())
    assert len(await repo.list_all()) == 2
