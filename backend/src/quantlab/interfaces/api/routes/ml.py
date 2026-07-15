"""ML/RL model registry endpoints: launch trainings and inspect results."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.ml import ML_ALGORITHMS, RL_ALGORITHMS, RL_TARGET, MlModel, ModelKind
from quantlab.domain.optimization import StudyStatus
from quantlab.interfaces.api.deps import AdminUser, ContainerDep
from quantlab.ml.labels import ALL_TARGETS

router = APIRouter(prefix="/ml/models", tags=["ml"])


class ModelCreate(BaseModel):
    kind: ModelKind
    target: str = "win"
    algorithm: str = "xgboost"
    symbol: Symbol
    timeframe: Timeframe
    config: dict[str, Any] = Field(default_factory=dict)


class ModelOut(BaseModel):
    id: uuid.UUID
    kind: ModelKind
    target: str
    algorithm: str
    symbol: Symbol
    timeframe: Timeframe
    status: StudyStatus
    config: dict[str, Any]
    metrics: dict[str, Any] | None
    artifact_path: str | None
    message: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_entity(cls, model: MlModel) -> "ModelOut":
        return cls(
            id=model.id,
            kind=model.kind,
            target=model.target,
            algorithm=model.algorithm,
            symbol=model.symbol,
            timeframe=model.timeframe,
            status=model.status,
            config=model.config,
            metrics=model.metrics,
            artifact_path=model.artifact_path,
            message=model.message,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


@router.post("", response_model=ModelOut, status_code=status.HTTP_202_ACCEPTED)
async def create_model(request: ModelCreate, container: ContainerDep, _: AdminUser) -> ModelOut:
    """Register a model and queue its training on a worker."""
    if request.kind == ModelKind.ML:
        if request.target not in ALL_TARGETS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown target: {request.target}. Valid: {sorted(ALL_TARGETS)}",
            )
        if request.algorithm not in ML_ALGORITHMS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown ML algorithm: {request.algorithm}. Valid: {ML_ALGORITHMS}",
            )
        target = request.target
    else:
        if request.algorithm not in RL_ALGORITHMS:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown RL algorithm: {request.algorithm}. Valid: {RL_ALGORITHMS}",
            )
        target = RL_TARGET
    if container.candle_store.coverage(request.symbol, request.timeframe) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"No local data for {request.symbol} {request.timeframe}; sync it first.",
        )
    model = MlModel(
        kind=request.kind,
        target=target,
        algorithm=request.algorithm,
        symbol=request.symbol,
        timeframe=request.timeframe,
        config=request.config,
    )
    async with container.ml_model_repository() as repo:
        model = await repo.create(model)
    await container.enqueue_training(model.id)
    return ModelOut.from_entity(model)


@router.get("", response_model=list[ModelOut])
async def list_models(container: ContainerDep) -> list[ModelOut]:
    """Every registered model, newest first."""
    async with container.ml_model_repository() as repo:
        models = await repo.list_all()
    return [ModelOut.from_entity(model) for model in models]


@router.get("/{model_id}", response_model=ModelOut)
async def get_model(model_id: uuid.UUID, container: ContainerDep) -> ModelOut:
    async with container.ml_model_repository() as repo:
        model = await repo.get(model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Model not found")
    return ModelOut.from_entity(model)
