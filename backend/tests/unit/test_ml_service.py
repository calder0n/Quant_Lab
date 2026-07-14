"""Tests for the ML training orchestration service."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from quantlab.application.event_bus import InMemoryEventBus
from quantlab.application.ports import MlModelRepository
from quantlab.application.services.ml import MlService, MlTrainingError
from quantlab.domain.events import DomainEvent
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.ml import MlModel, ModelKind, ModelTrained, ModelTrainingFailed
from quantlab.domain.optimization import StudyStatus
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from tests.factories import make_market_data


class InMemoryMlRepo(MlModelRepository):
    def __init__(self, models: dict[uuid.UUID, MlModel]) -> None:
        self._models = models

    async def create(self, model: MlModel) -> MlModel:
        self._models[model.id] = model
        return model

    async def get(self, model_id: uuid.UUID) -> MlModel | None:
        return self._models.get(model_id)

    async def list_all(self) -> list[MlModel]:
        return list(self._models.values())

    async def update(self, model: MlModel) -> MlModel:
        self._models[model.id] = model
        return model


def build_service(
    tmp_path: Path, bars: int = 1500
) -> tuple[MlService, dict[uuid.UUID, MlModel], list[DomainEvent]]:
    models: dict[uuid.UUID, MlModel] = {}

    @asynccontextmanager
    async def repositories() -> AsyncIterator[MlModelRepository]:
        yield InMemoryMlRepo(models)

    bus = InMemoryEventBus()
    events: list[DomainEvent] = []

    async def record(event: DomainEvent) -> None:
        events.append(event)

    bus.subscribe(DomainEvent, record)
    store = ParquetCandleStore(tmp_path / "candles")
    store.append(Symbol.EURUSD, Timeframe.H1, make_market_data(bars))
    service = MlService(
        store=store,
        repositories=repositories,
        event_bus=bus,
        artifacts_dir=tmp_path / "models",
    )
    return service, models, events


def make_model(**overrides: object) -> MlModel:
    defaults: dict[str, object] = {
        "kind": ModelKind.ML,
        "target": "win",
        "algorithm": "xgboost",
        "symbol": Symbol.EURUSD,
        "timeframe": Timeframe.H1,
        "config": {"n_estimators": 20, "horizon": 6},
    }
    defaults.update(overrides)
    return MlModel(**defaults)  # type: ignore[arg-type]


async def test_supervised_training_completes_with_metrics(tmp_path: Path) -> None:
    service, models, events = build_service(tmp_path)
    model = make_model()
    models[model.id] = model

    result = await service.train(model.id)

    assert result.status == StudyStatus.COMPLETED
    assert result.metrics is not None
    assert result.metrics["task"] == "classification"
    assert 0.0 <= result.metrics["auc"] <= 1.0
    assert "feature_importances" in result.metrics
    assert result.artifact_path is not None and Path(result.artifact_path).exists()
    assert any(isinstance(e, ModelTrained) for e in events)


async def test_regression_target_uses_regression_metrics(tmp_path: Path) -> None:
    service, models, _ = build_service(tmp_path)
    model = make_model(target="expected_move", algorithm="lightgbm")
    models[model.id] = model
    result = await service.train(model.id)
    assert result.status == StudyStatus.COMPLETED
    assert result.metrics is not None
    assert result.metrics["task"] == "regression"
    assert "mae" in result.metrics and "r2" in result.metrics


async def test_rl_training_evaluates_on_held_out_tail(tmp_path: Path) -> None:
    service, models, _ = build_service(tmp_path)
    model = make_model(
        kind=ModelKind.RL,
        target="policy",
        algorithm="ppo",
        config={"timesteps": 400, "n_steps": 64},
    )
    models[model.id] = model
    result = await service.train(model.id)
    assert result.status == StudyStatus.COMPLETED
    assert result.metrics is not None
    assert "eval_total_return" in result.metrics
    assert result.metrics["eval_bars"] > 0
    assert result.artifact_path is not None and Path(result.artifact_path).exists()


async def test_unknown_algorithm_fails_the_model(tmp_path: Path) -> None:
    service, models, events = build_service(tmp_path)
    model = make_model(algorithm="nope")
    models[model.id] = model
    result = await service.train(model.id)
    assert result.status == StudyStatus.FAILED
    assert "nope" in (result.message or "")
    assert any(isinstance(e, ModelTrainingFailed) for e in events)


async def test_insufficient_data_fails_the_model(tmp_path: Path) -> None:
    service, models, _ = build_service(tmp_path, bars=200)
    model = make_model()
    models[model.id] = model
    result = await service.train(model.id)
    assert result.status == StudyStatus.FAILED
    assert "at least" in (result.message or "")


async def test_unknown_model_raises(tmp_path: Path) -> None:
    service, _, _ = build_service(tmp_path)
    with pytest.raises(MlTrainingError):
        await service.train(uuid.uuid4())
