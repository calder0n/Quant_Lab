"""Tests for the SQLAlchemy optimization repository (in-memory SQLite)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from quantlab.domain.backtest import BacktestMetrics
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.objective import ObjectiveConfig
from quantlab.domain.optimization import OptimizationStudy, OptimizationTrial, StudyStatus
from quantlab.infrastructure.db.base import Base
from quantlab.infrastructure.db.repositories.optimization import (
    SqlAlchemyOptimizationRepository,
)


@pytest.fixture
async def repo() -> AsyncIterator[SqlAlchemyOptimizationRepository]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield SqlAlchemyOptimizationRepository(session)
    await engine.dispose()


def make_study(**overrides: object) -> OptimizationStudy:
    defaults: dict[str, object] = {
        "strategy_id": "ema_cross",
        "symbol": Symbol.EURUSD,
        "timeframe": Timeframe.H1,
        "optimizer": "optuna",
        "n_trials": 100,
        "objective": ObjectiveConfig(),
    }
    defaults.update(overrides)
    return OptimizationStudy(**defaults)  # type: ignore[arg-type]


async def test_create_and_get_study(repo: SqlAlchemyOptimizationRepository) -> None:
    study = await repo.create_study(make_study(seed=7))
    fetched = await repo.get_study(study.id)
    assert fetched is not None
    assert fetched.strategy_id == "ema_cross"
    assert fetched.status == StudyStatus.PENDING
    assert fetched.objective == ObjectiveConfig()
    assert fetched.seed == 7
    assert fetched.created_at is not None


async def test_get_missing_study_returns_none(repo: SqlAlchemyOptimizationRepository) -> None:
    assert await repo.get_study(uuid.uuid4()) is None


async def test_update_study_progress(repo: SqlAlchemyOptimizationRepository) -> None:
    study = await repo.create_study(make_study())
    study.status = StudyStatus.COMPLETED
    study.trials_completed = 100
    study.best_score = 0.71
    study.best_params = {"fast_period": 9}
    updated = await repo.update_study(study)
    assert updated.status == StudyStatus.COMPLETED
    assert updated.best_params == {"fast_period": 9}
    fetched = await repo.get_study(study.id)
    assert fetched is not None and fetched.best_score == 0.71


async def test_list_studies_newest_first(repo: SqlAlchemyOptimizationRepository) -> None:
    await repo.create_study(make_study(strategy_id="rsi"))
    await repo.create_study(make_study(strategy_id="macd"))
    listed = await repo.list_studies()
    assert len(listed) == 2
    assert {s.strategy_id for s in listed} == {"rsi", "macd"}


async def test_trials_are_ranked_by_score(repo: SqlAlchemyOptimizationRepository) -> None:
    study = await repo.create_study(make_study())
    for number, score in [(1, 0.2), (2, 0.9), (3, -1.0), (4, 0.5)]:
        await repo.add_trial(
            OptimizationTrial(
                study_id=study.id,
                number=number,
                params={"fast_period": number},
                score=score,
                metrics=BacktestMetrics(trades=number),
            )
        )
    top = await repo.top_trials(study.id, limit=3)
    assert [t.score for t in top] == [0.9, 0.5, 0.2]
    assert top[0].params == {"fast_period": 2}
    assert top[0].metrics.trades == 2
