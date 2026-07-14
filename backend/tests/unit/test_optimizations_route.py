"""Tests for the optimizations and workers API routes."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import ClassVar

import httpx
from fastapi import FastAPI

from quantlab.application.ports import OptimizationRepository
from quantlab.config import Settings
from quantlab.domain.backtest import BacktestMetrics
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.objective import ObjectiveConfig
from quantlab.domain.optimization import OptimizationStudy, OptimizationTrial, StudyStatus
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from quantlab.interfaces.api.app import create_app
from quantlab.strategies.registry import StrategyRegistry
from tests.factories import make_market_data
from tests.unit.test_optimization_service import InMemoryOptimizationRepo


class FakeOptimizationService:
    optimizer_names: ClassVar[list[str]] = ["optuna", "random"]


class FakeRedis:
    def __init__(self, heartbeat: str | None = None) -> None:
        self.heartbeat = heartbeat

    async def get(self, key: str) -> str | None:
        return self.heartbeat


class OptimizationsStubContainer:
    def __init__(self, settings: Settings, tmp_path: object) -> None:
        self.settings = settings
        self.strategy_registry = StrategyRegistry().discover()
        self.optimization_service = FakeOptimizationService()
        self.candle_store = ParquetCandleStore(tmp_path / "candles")  # type: ignore[operator]
        self.candle_store.append(Symbol.EURUSD, Timeframe.H1, make_market_data(100))
        self.studies: dict[uuid.UUID, OptimizationStudy] = {}
        self.trials: list[OptimizationTrial] = []
        self.enqueued: list[uuid.UUID] = []
        self.redis = FakeRedis()

    @asynccontextmanager
    async def optimization_repository(self) -> AsyncIterator[OptimizationRepository]:
        yield InMemoryOptimizationRepo(self.studies, self.trials)

    async def enqueue_optimization(self, study_id: uuid.UUID) -> None:
        self.enqueued.append(study_id)


def build_client(app: FastAPI, container: OptimizationsStubContainer) -> httpx.AsyncClient:
    app.state.container = container
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


VALID_BODY = {"strategy_id": "ema_cross", "symbol": "EURUSD", "timeframe": "H1", "n_trials": 50}


async def test_create_study_persists_and_enqueues(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = OptimizationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post("/api/v1/optimizations", json=VALID_BODY)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["n_trials"] == 50
    study_id = uuid.UUID(body["id"])
    assert study_id in container.studies
    assert container.enqueued == [study_id]


async def test_create_study_rejects_unknown_strategy(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = OptimizationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post(
            "/api/v1/optimizations", json={**VALID_BODY, "strategy_id": "nope"}
        )
    assert response.status_code == 404
    assert container.enqueued == []


async def test_create_study_rejects_unknown_optimizer(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = OptimizationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post(
            "/api/v1/optimizations", json={**VALID_BODY, "optimizer": "genetic"}
        )
    assert response.status_code == 422
    assert "genetic" in response.json()["detail"]


async def test_create_study_requires_local_data(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = OptimizationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post("/api/v1/optimizations", json={**VALID_BODY, "symbol": "US30"})
    assert response.status_code == 404
    assert "No local data" in response.json()["detail"]


async def test_create_study_rejects_bad_objective(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = OptimizationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post(
            "/api/v1/optimizations",
            json={**VALID_BODY, "objective": {"weights": {"nope": 1.0}}},
        )
    assert response.status_code == 422


async def test_list_get_and_trials(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = OptimizationsStubContainer(settings, tmp_path)
    study = OptimizationStudy(
        strategy_id="rsi",
        symbol=Symbol.EURUSD,
        timeframe=Timeframe.H1,
        optimizer="optuna",
        n_trials=10,
        objective=ObjectiveConfig(),
        status=StudyStatus.COMPLETED,
        best_score=0.42,
    )
    container.studies[study.id] = study
    container.trials.append(
        OptimizationTrial(
            study_id=study.id,
            number=1,
            params={"rsi_period": 14},
            score=0.42,
            metrics=BacktestMetrics(trades=50),
        )
    )
    async with build_client(app, container) as client:
        listed = await client.get("/api/v1/optimizations")
        detail = await client.get(f"/api/v1/optimizations/{study.id}")
        trials = await client.get(f"/api/v1/optimizations/{study.id}/trials")
        missing = await client.get(f"/api/v1/optimizations/{uuid.uuid4()}")
        missing_trials = await client.get(f"/api/v1/optimizations/{uuid.uuid4()}/trials")
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert detail.json()["best_score"] == 0.42
    assert trials.json()[0]["params"] == {"rsi_period": 14}
    assert missing.status_code == 404
    assert missing_trials.status_code == 404


async def test_workers_status_offline_without_heartbeat(
    settings: Settings, tmp_path: object
) -> None:
    app = create_app(settings)
    container = OptimizationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.get("/api/v1/workers")
    assert response.json() == {
        "online": False,
        "jobs_complete": 0,
        "jobs_failed": 0,
        "jobs_ongoing": 0,
        "queued": 0,
        "heartbeat": None,
    }


async def test_workers_status_parses_heartbeat(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = OptimizationsStubContainer(settings, tmp_path)
    container.redis = FakeRedis(
        "Jul-14 16:20:11 j_complete=3 j_failed=1 j_retried=0 j_ongoing=1 queued=2"
    )
    async with build_client(app, container) as client:
        body = (await client.get("/api/v1/workers")).json()
    assert body["online"] is True
    assert body["jobs_complete"] == 3
    assert body["jobs_failed"] == 1
    assert body["jobs_ongoing"] == 1
    assert body["queued"] == 2
