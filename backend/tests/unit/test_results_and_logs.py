"""Tests for global ranking/heatmap queries, results routes and the log buffer."""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from quantlab.application.ports import OptimizationRepository
from quantlab.config import Settings
from quantlab.domain.backtest import BacktestMetrics
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.objective import ObjectiveConfig
from quantlab.domain.optimization import OptimizationStudy, OptimizationTrial, StudyStatus
from quantlab.infrastructure.db.base import Base
from quantlab.infrastructure.db.repositories.optimization import (
    SqlAlchemyOptimizationRepository,
)
from quantlab.infrastructure.logging.redis_handler import (
    LOG_KEY,
    RedisLogHandler,
    teardown_dashboard_logging,
)
from quantlab.interfaces.api.app import create_app
from tests.unit.test_optimization_service import InMemoryOptimizationRepo


def make_study(symbol: Symbol, timeframe: Timeframe, best: float | None) -> OptimizationStudy:
    return OptimizationStudy(
        strategy_id="ema_cross",
        symbol=symbol,
        timeframe=timeframe,
        optimizer="optuna",
        n_trials=10,
        objective=ObjectiveConfig(),
        status=StudyStatus.COMPLETED,
        best_score=best,
    )


# -- SQL repository queries -------------------------------------------------------


@pytest.fixture
async def sql_repo() -> AsyncIterator[SqlAlchemyOptimizationRepository]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield SqlAlchemyOptimizationRepository(session)
    await engine.dispose()


async def test_global_ranking_joins_trials_with_studies(
    sql_repo: SqlAlchemyOptimizationRepository,
) -> None:
    study_a = await sql_repo.create_study(make_study(Symbol.EURUSD, Timeframe.H1, 0.5))
    study_b = await sql_repo.create_study(make_study(Symbol.XAUUSD, Timeframe.H4, 0.9))
    pending = make_study(Symbol.US30, Timeframe.D1, None)
    pending.status = StudyStatus.PENDING
    await sql_repo.create_study(pending)
    for study, scores in ((study_a, [0.1, 0.5]), (study_b, [0.9, -1.0]), (pending, [2.0])):
        for i, score in enumerate(scores):
            await sql_repo.add_trial(
                OptimizationTrial(
                    study_id=study.id,
                    number=i + 1,
                    params={"x": i},
                    score=score,
                    metrics=BacktestMetrics(trades=10),
                )
            )
    ranked = await sql_repo.global_ranking(limit=3)
    # pending study's 2.0 trial is excluded; best completed trials first
    assert [round(trial.score, 2) for trial, _ in ranked] == [0.9, 0.5, 0.1]
    assert ranked[0][1].symbol == Symbol.XAUUSD


async def test_heatmap_aggregates_best_score_per_cell(
    sql_repo: SqlAlchemyOptimizationRepository,
) -> None:
    await sql_repo.create_study(make_study(Symbol.EURUSD, Timeframe.H1, 0.3))
    await sql_repo.create_study(make_study(Symbol.EURUSD, Timeframe.H1, 0.7))
    await sql_repo.create_study(make_study(Symbol.XAUUSD, Timeframe.D1, -0.2))
    cells = {(s, tf): (best, count) for s, tf, best, count in await sql_repo.heatmap()}
    assert cells[("EURUSD", "H1")] == (0.7, 2)
    assert cells[("XAUUSD", "D1")] == (-0.2, 1)


# -- results/logs routes ------------------------------------------------------------


class FakeRedisLrange:
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        assert key == LOG_KEY
        return self.lines[start : stop + 1]


class ResultsStubContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.studies: dict[uuid.UUID, OptimizationStudy] = {}
        self.trials: list[OptimizationTrial] = []
        self.redis = FakeRedisLrange([])

    @asynccontextmanager
    async def optimization_repository(self) -> AsyncIterator[OptimizationRepository]:
        yield InMemoryOptimizationRepo(self.studies, self.trials)


def build_client(app: FastAPI, container: ResultsStubContainer) -> httpx.AsyncClient:
    app.state.container = container
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_ranking_and_heatmap_routes(settings: Settings) -> None:
    app = create_app(settings)
    container = ResultsStubContainer(settings)
    study = make_study(Symbol.EURUSD, Timeframe.H1, 0.4)
    container.studies[study.id] = study
    container.trials.append(
        OptimizationTrial(
            study_id=study.id,
            number=1,
            params={"fast_period": 9},
            score=0.4,
            metrics=BacktestMetrics(trades=42),
        )
    )
    async with build_client(app, container) as client:
        ranking = await client.get("/api/v1/results/ranking")
        heatmap = await client.get("/api/v1/results/heatmap")
    assert ranking.status_code == 200
    assert ranking.json()[0]["strategy_id"] == "ema_cross"
    assert ranking.json()[0]["params"] == {"fast_period": 9}
    assert heatmap.json() == [
        {"symbol": "EURUSD", "timeframe": "H1", "best_score": 0.4, "studies": 1}
    ]


async def test_logs_route_parses_entries_and_tolerates_garbage(settings: Settings) -> None:
    app = create_app(settings)
    container = ResultsStubContainer(settings)
    container.redis = FakeRedisLrange(
        [
            json.dumps(
                {
                    "time": "2026-07-15T10:00:00+00:00",
                    "level": "INFO",
                    "source": "worker",
                    "logger": "quantlab.x",
                    "message": "Study completed",
                }
            ),
            "not-json",
        ]
    )
    async with build_client(app, container) as client:
        response = await client.get("/api/v1/logs")
    body = response.json()
    assert len(body) == 2
    assert body[0]["source"] == "worker"
    assert body[0]["message"] == "Study completed"
    assert body[1]["message"] == "not-json"


# -- redis log handler ----------------------------------------------------------------


class FakePipeline:
    def __init__(self, sink: list[tuple[str, Any]]) -> None:
        self._sink = sink
        self._commands: list[tuple[str, Any]] = []

    def lpush(self, key: str, value: str) -> None:
        self._commands.append(("lpush", value))

    def ltrim(self, key: str, start: int, stop: int) -> None:
        self._commands.append(("ltrim", (start, stop)))

    def execute(self) -> None:
        self._sink.extend(self._commands)


class FakeSyncRedis:
    def __init__(self) -> None:
        self.commands: list[tuple[str, Any]] = []

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self.commands)


def test_handler_pushes_formatted_entries() -> None:
    client = FakeSyncRedis()
    handler = RedisLogHandler(client, source="worker")
    logger = logging.getLogger("quantlab.test_handler")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("Sync completed: %s", "EURUSD")
    finally:
        logger.removeHandler(handler)
    pushes = [value for op, value in client.commands if op == "lpush"]
    assert len(pushes) == 1
    entry = json.loads(pushes[0])
    assert entry["message"] == "Sync completed: EURUSD"
    assert entry["source"] == "worker"
    assert ("ltrim", (0, 499)) in client.commands


def test_handler_swallows_broken_client() -> None:
    class Broken:
        def pipeline(self) -> Any:
            raise ConnectionError("redis down")

    handler = RedisLogHandler(Broken(), source="api")
    record = logging.LogRecord("quantlab", logging.INFO, __file__, 1, "msg", None, None)
    handler.emit(record)  # must not raise


def test_teardown_accepts_none() -> None:
    teardown_dashboard_logging(None)
