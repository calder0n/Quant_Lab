"""Optimization study endpoints: launch, list, inspect, rank."""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from quantlab.domain.backtest import BacktestMetrics
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.objective import InvalidObjectiveError, ObjectiveConfig
from quantlab.domain.optimization import OptimizationStudy, OptimizationTrial, StudyStatus
from quantlab.interfaces.api.deps import AdminUser, ContainerDep
from quantlab.strategies.base import ParamValue
from quantlab.strategies.registry import UnknownStrategyError

router = APIRouter(prefix="/optimizations", tags=["optimizations"])


class ObjectiveIn(BaseModel):
    weights: dict[str, float] | None = None
    min_trades: int = Field(default=30, ge=0)
    max_drawdown_limit: float | None = Field(default=None, gt=0.0, le=1.0)

    def to_config(self) -> ObjectiveConfig:
        if self.weights is None:
            return ObjectiveConfig(
                min_trades=self.min_trades, max_drawdown_limit=self.max_drawdown_limit
            )
        return ObjectiveConfig(
            weights=self.weights,
            min_trades=self.min_trades,
            max_drawdown_limit=self.max_drawdown_limit,
        )


class StudyCreate(BaseModel):
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    optimizer: str = "optuna"
    n_trials: int = Field(200, ge=5, le=100_000)
    objective: ObjectiveIn | None = None
    seed: int | None = None
    start: datetime | None = None
    end: datetime | None = None


class StudyOut(BaseModel):
    id: uuid.UUID
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    optimizer: str
    status: StudyStatus
    n_trials: int
    trials_completed: int
    best_score: float | None
    best_params: dict[str, ParamValue] | None
    message: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_entity(cls, study: OptimizationStudy) -> "StudyOut":
        return cls(
            id=study.id,
            strategy_id=study.strategy_id,
            symbol=study.symbol,
            timeframe=study.timeframe,
            optimizer=study.optimizer,
            status=study.status,
            n_trials=study.n_trials,
            trials_completed=study.trials_completed,
            best_score=study.best_score,
            best_params=study.best_params,
            message=study.message,
            created_at=study.created_at,
            updated_at=study.updated_at,
        )


class TrialOut(BaseModel):
    number: int
    score: float
    params: dict[str, ParamValue]
    metrics: BacktestMetrics

    @classmethod
    def from_entity(cls, trial: OptimizationTrial) -> "TrialOut":
        return cls(
            number=trial.number, score=trial.score, params=trial.params, metrics=trial.metrics
        )


@router.post("", response_model=StudyOut, status_code=status.HTTP_202_ACCEPTED)
async def create_study(request: StudyCreate, container: ContainerDep, _: AdminUser) -> StudyOut:
    """Persist a study and queue it for execution by a worker."""
    try:
        container.strategy_registry.get(request.strategy_id)
    except UnknownStrategyError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Unknown strategy: {request.strategy_id}"
        ) from exc
    if request.optimizer not in container.optimization_service.optimizer_names:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown optimizer: {request.optimizer}. "
            f"Available: {container.optimization_service.optimizer_names}",
        )
    if container.candle_store.coverage(request.symbol, request.timeframe) is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"No local data for {request.symbol} {request.timeframe}; sync it first.",
        )
    try:
        objective = (request.objective or ObjectiveIn()).to_config()
    except InvalidObjectiveError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    study = OptimizationStudy(
        strategy_id=request.strategy_id,
        symbol=request.symbol,
        timeframe=request.timeframe,
        optimizer=request.optimizer,
        n_trials=request.n_trials,
        objective=objective,
        seed=request.seed,
        range_start=request.start,
        range_end=request.end,
    )
    async with container.optimization_repository() as repo:
        study = await repo.create_study(study)
    await container.enqueue_optimization(study.id)
    return StudyOut.from_entity(study)


@router.get("", response_model=list[StudyOut])
async def list_studies(container: ContainerDep) -> list[StudyOut]:
    """Every study, newest first."""
    async with container.optimization_repository() as repo:
        studies = await repo.list_studies()
    return [StudyOut.from_entity(study) for study in studies]


@router.get("/{study_id}", response_model=StudyOut)
async def get_study(study_id: uuid.UUID, container: ContainerDep) -> StudyOut:
    async with container.optimization_repository() as repo:
        study = await repo.get_study(study_id)
    if study is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Study not found")
    return StudyOut.from_entity(study)


@router.get("/{study_id}/trials", response_model=list[TrialOut])
async def top_trials(
    study_id: uuid.UUID,
    container: ContainerDep,
    limit: int = Query(10, ge=1, le=200),
) -> list[TrialOut]:
    """Best trials of a study, ranked by objective score."""
    async with container.optimization_repository() as repo:
        if await repo.get_study(study_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Study not found")
        trials = await repo.top_trials(study_id, limit=limit)
    return [TrialOut.from_entity(trial) for trial in trials]
