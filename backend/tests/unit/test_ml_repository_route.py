"""Tests for the ML model repository (SQLite) and API routes."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from quantlab.application.ports import MlModelRepository
from quantlab.config import Settings
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.ml import MlModel, ModelKind
from quantlab.domain.optimization import StudyStatus
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from quantlab.infrastructure.db.base import Base
from quantlab.infrastructure.db.repositories.ml import SqlAlchemyMlModelRepository
from quantlab.interfaces.api.app import create_app
from tests.factories import make_market_data
from tests.unit.test_ml_service import InMemoryMlRepo


@pytest.fixture
async def repo() -> AsyncIterator[SqlAlchemyMlModelRepository]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield SqlAlchemyMlModelRepository(session)
    await engine.dispose()


def make_model() -> MlModel:
    return MlModel(
        kind=ModelKind.ML,
        target="win",
        algorithm="xgboost",
        symbol=Symbol.EURUSD,
        timeframe=Timeframe.H1,
        config={"horizon": 12},
    )


async def test_repository_crud(repo: SqlAlchemyMlModelRepository) -> None:
    model = await repo.create(make_model())
    fetched = await repo.get(model.id)
    assert fetched is not None
    assert fetched.kind == ModelKind.ML
    assert fetched.config == {"horizon": 12}

    fetched.status = StudyStatus.COMPLETED
    fetched.metrics = {"auc": 0.61}
    fetched.artifact_path = "/data/models/x.joblib"
    await repo.update(fetched)
    reloaded = await repo.get(model.id)
    assert reloaded is not None
    assert reloaded.metrics == {"auc": 0.61}
    assert await repo.get(uuid.uuid4()) is None
    assert len(await repo.list_all()) == 1


class MlStubContainer:
    def __init__(self, settings: Settings, tmp_path: object) -> None:
        self.settings = settings
        self.candle_store = ParquetCandleStore(tmp_path / "candles")  # type: ignore[operator]
        self.candle_store.append(Symbol.EURUSD, Timeframe.H1, make_market_data(100))
        self.models: dict[uuid.UUID, MlModel] = {}
        self.enqueued: list[uuid.UUID] = []

    @asynccontextmanager
    async def ml_model_repository(self) -> AsyncIterator[MlModelRepository]:
        yield InMemoryMlRepo(self.models)

    async def enqueue_training(self, model_id: uuid.UUID) -> None:
        self.enqueued.append(model_id)


def build_client(app: FastAPI, container: MlStubContainer) -> httpx.AsyncClient:
    app.state.container = container
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


VALID_BODY = {
    "kind": "ml",
    "target": "win",
    "algorithm": "xgboost",
    "symbol": "EURUSD",
    "timeframe": "H1",
}


async def test_create_model_persists_and_enqueues(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = MlStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post("/api/v1/ml/models", json=VALID_BODY)
    assert response.status_code == 202
    model_id = uuid.UUID(response.json()["id"])
    assert model_id in container.models
    assert container.enqueued == [model_id]


async def test_rl_creation_forces_policy_target(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = MlStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        response = await client.post(
            "/api/v1/ml/models",
            json={**VALID_BODY, "kind": "rl", "algorithm": "ppo", "target": "ignored"},
        )
    assert response.status_code == 202
    assert response.json()["target"] == "policy"


async def test_create_model_validations(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = MlStubContainer(settings, tmp_path)
    async with build_client(app, container) as client:
        bad_target = await client.post("/api/v1/ml/models", json={**VALID_BODY, "target": "nope"})
        bad_algo = await client.post("/api/v1/ml/models", json={**VALID_BODY, "algorithm": "nope"})
        bad_rl_algo = await client.post(
            "/api/v1/ml/models", json={**VALID_BODY, "kind": "rl", "algorithm": "dqn"}
        )
        no_data = await client.post("/api/v1/ml/models", json={**VALID_BODY, "symbol": "US30"})
    assert bad_target.status_code == 422
    assert bad_algo.status_code == 422
    assert bad_rl_algo.status_code == 422
    assert no_data.status_code == 404
    assert container.enqueued == []


async def test_list_and_get_models(settings: Settings, tmp_path: object) -> None:
    app = create_app(settings)
    container = MlStubContainer(settings, tmp_path)
    model = make_model()
    model.status = StudyStatus.COMPLETED
    model.metrics = {"auc": 0.6}
    container.models[model.id] = model
    async with build_client(app, container) as client:
        listed = await client.get("/api/v1/ml/models")
        detail = await client.get(f"/api/v1/ml/models/{model.id}")
        missing = await client.get(f"/api/v1/ml/models/{uuid.uuid4()}")
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert detail.json()["metrics"]["auc"] == 0.6
    assert missing.status_code == 404
