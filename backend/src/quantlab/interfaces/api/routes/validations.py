"""Validation endpoints: launch and inspect walk-forward, Monte Carlo and stress runs."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.objective import InvalidObjectiveError, ObjectiveConfig
from quantlab.domain.optimization import StudyStatus
from quantlab.domain.validation import ValidationKind, ValidationRun
from quantlab.interfaces.api.deps import ContainerDep
from quantlab.strategies.base import InvalidParameterError, ParamValue
from quantlab.strategies.registry import UnknownStrategyError

router = APIRouter(prefix="/validations", tags=["validations"])


class ValidationCreate(BaseModel):
    kind: ValidationKind
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    params: dict[str, ParamValue] | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class ValidationOut(BaseModel):
    id: uuid.UUID
    kind: ValidationKind
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    status: StudyStatus
    params: dict[str, ParamValue] | None
    config: dict[str, Any]
    result: dict[str, Any] | None
    message: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_entity(cls, run: ValidationRun) -> "ValidationOut":
        return cls(
            id=run.id,
            kind=run.kind,
            strategy_id=run.strategy_id,
            symbol=run.symbol,
            timeframe=run.timeframe,
            status=run.status,
            params=run.params,
            config=run.config,
            result=run.result,
            message=run.message,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )


@router.post("", response_model=ValidationOut, status_code=status.HTTP_202_ACCEPTED)
async def create_validation(request: ValidationCreate, container: ContainerDep) -> ValidationOut:
    """Persist a validation run and queue it for execution by a worker."""
    try:
        strategy_class = container.strategy_registry.get(request.strategy_id)
        if request.params is not None:
            strategy_class(**request.params)  # fail fast on bad params
    except UnknownStrategyError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Unknown strategy: {request.strategy_id}"
        ) from exc
    except InvalidParameterError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    if container.candle_store.coverage(request.symbol, request.timeframe) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"No local data for {request.symbol} {request.timeframe}; sync it first.",
        )
    if request.kind == ValidationKind.WALK_FORWARD:
        try:
            ObjectiveConfig.from_dict(request.config.get("objective") or {})
        except InvalidObjectiveError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
        optimizer = str(request.config.get("optimizer", "optuna"))
        if optimizer not in container.validation_service.optimizer_names:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown optimizer: {optimizer}"
            )

    run = ValidationRun(
        kind=request.kind,
        strategy_id=request.strategy_id,
        symbol=request.symbol,
        timeframe=request.timeframe,
        params=request.params,
        config=request.config,
    )
    async with container.validation_repository() as repo:
        run = await repo.create(run)
    await container.enqueue_validation(run.id)
    return ValidationOut.from_entity(run)


@router.get("", response_model=list[ValidationOut])
async def list_validations(container: ContainerDep) -> list[ValidationOut]:
    """Every validation run, newest first."""
    async with container.validation_repository() as repo:
        runs = await repo.list_all()
    return [ValidationOut.from_entity(run) for run in runs]


@router.get("/{run_id}", response_model=ValidationOut)
async def get_validation(run_id: uuid.UUID, container: ContainerDep) -> ValidationOut:
    async with container.validation_repository() as repo:
        run = await repo.get(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Validation not found")
    return ValidationOut.from_entity(run)
