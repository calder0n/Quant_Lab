"""Tests for the validations API routes."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from quantlab.application.ports import ValidationRepository
from quantlab.config import Settings
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.optimization import StudyStatus
from quantlab.domain.validation import ValidationKind, ValidationRun
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from quantlab.interfaces.api.app import create_app
from quantlab.strategies.registry import StrategyRegistry
from tests.factories import make_market_data
from tests.unit.test_validation_service import InMemoryValidationRepo


class FakeValidationService:
    optimizer_names = ("optuna", "random")


class ValidationsStubContainer:
    def __init__(self, settings: Settings, tmp_path: object) -> None:
        self.settings = settings
        self.strategy_registry = StrategyRegistry().discover()
        self.validation_service = FakeValidationService()
        self.candle_store = ParquetCandleStore(tmp_path / "candles")  # type: ignore[operator]
        self.candle_store.append(Symbol.EURUSD, Timeframe.H1, make_market_data(100))
        self.runs: dict[uuid.UUID, ValidationRun] = {}
        self.enqueued: list[uuid.UUID] = []

    @asynccontextmanager
    async def validation_repository(self) -> AsyncIterator[ValidationRepository]:
        yield InMemoryValidationRepo(self.runs)

    async def enqueue_validation(self, run_id: uuid.UUID) -> None:
        self.enqueued.append(run_id)


def build_client(app: FastAPI, container: ValidationsStubContainer) -> httpx.AsyncClient:
    app.state.container = container
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


VALID_BODY = {
    "kind": "walk_forward",
    "strategy_id": "ema_cross",
    "symbol": "EURUSD",
    "timeframe": "H1",
}


async def test_create_validation_persists_and_enqueues(
    settings: Settings, tmp_path: object
) -> None:
    app = create_app(settings)
    container = ValidationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post("/api/v1/validations", json=VALID_BODY)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    run_id = uuid.UUID(body["id"])
    assert run_id in container.runs
    assert container.enqueued == [run_id]


async def test_create_validation_rejects_unknown_strategy(
    settings: Settings, tmp_path: object
) -> None:
    app = create_app(settings)
    container = ValidationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post(
            "/api/v1/validations", json={**VALID_BODY, "strategy_id": "nope"}
        )
    assert response.status_code == 404
    assert container.enqueued == []


async def test_create_validation_rejects_bad_params(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = ValidationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post(
            "/api/v1/validations", json={**VALID_BODY, "params": {"bogus": 1}}
        )
    assert response.status_code == 422


async def test_create_validation_requires_local_data(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = ValidationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post("/api/v1/validations", json={**VALID_BODY, "symbol": "US30"})
    assert response.status_code == 404
    assert "No local data" in response.json()["detail"]


async def test_create_walk_forward_validates_objective_and_optimizer(
    settings: Settings, tmp_path: object
) -> None:
    app = create_app(settings)
    container = ValidationsStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        bad_objective = await client.post(
            "/api/v1/validations",
            json={**VALID_BODY, "config": {"objective": {"weights": {"nope": 1.0}}}},
        )
        bad_optimizer = await client.post(
            "/api/v1/validations", json={**VALID_BODY, "config": {"optimizer": "genetic"}}
        )
    assert bad_objective.status_code == 422
    assert bad_optimizer.status_code == 422


async def test_list_and_get_validations(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = ValidationsStubContainer(settings, tmp_path)
    run = ValidationRun(
        kind=ValidationKind.MONTE_CARLO,
        strategy_id="rsi",
        symbol=Symbol.EURUSD,
        timeframe=Timeframe.H1,
        status=StudyStatus.COMPLETED,
        result={"kind": "monte_carlo", "prob_loss": 0.1},
    )
    container.runs[run.id] = run
    async with build_client(app, container) as client:
        listed = await client.get("/api/v1/validations")
        detail = await client.get(f"/api/v1/validations/{run.id}")
        missing = await client.get(f"/api/v1/validations/{uuid.uuid4()}")
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert detail.json()["result"]["prob_loss"] == 0.1
    assert missing.status_code == 404
