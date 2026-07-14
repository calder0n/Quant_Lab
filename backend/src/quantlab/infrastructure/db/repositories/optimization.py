"""SQLAlchemy implementation of the ``OptimizationRepository`` port."""

import uuid
from dataclasses import asdict
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantlab.application.ports import OptimizationRepository
from quantlab.domain.backtest import BacktestMetrics
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.objective import ObjectiveConfig
from quantlab.domain.optimization import OptimizationStudy, OptimizationTrial, StudyStatus
from quantlab.infrastructure.db.models.optimization import (
    OptimizationStudyRecord,
    OptimizationTrialRecord,
)
from quantlab.strategies.base import ParamValue


def _study_to_entity(record: OptimizationStudyRecord) -> OptimizationStudy:
    return OptimizationStudy(
        id=record.id,
        strategy_id=record.strategy_id,
        symbol=Symbol(record.symbol),
        timeframe=Timeframe(record.timeframe),
        optimizer=record.optimizer,
        status=StudyStatus(record.status),
        n_trials=record.n_trials,
        trials_completed=record.trials_completed,
        objective=ObjectiveConfig.from_dict(record.objective),
        best_score=record.best_score,
        best_params=cast(dict[str, ParamValue] | None, record.best_params),
        seed=record.seed,
        range_start=record.range_start,
        range_end=record.range_end,
        message=record.message,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _trial_to_entity(record: OptimizationTrialRecord) -> OptimizationTrial:
    return OptimizationTrial(
        id=record.id,
        study_id=record.study_id,
        number=record.number,
        params=cast(dict[str, ParamValue], record.params),
        score=record.score,
        metrics=BacktestMetrics(**record.metrics),
        created_at=record.created_at,
    )


def _apply(record: OptimizationStudyRecord, study: OptimizationStudy) -> None:
    record.strategy_id = study.strategy_id
    record.symbol = study.symbol.value
    record.timeframe = study.timeframe.value
    record.optimizer = study.optimizer
    record.status = study.status.value
    record.n_trials = study.n_trials
    record.trials_completed = study.trials_completed
    record.objective = study.objective.to_dict()
    record.best_score = study.best_score
    record.best_params = study.best_params
    record.seed = study.seed
    record.range_start = study.range_start
    record.range_end = study.range_end
    record.message = study.message


class SqlAlchemyOptimizationRepository(OptimizationRepository):
    """Optimization studies and trials persisted in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_study(self, study: OptimizationStudy) -> OptimizationStudy:
        record = OptimizationStudyRecord(id=study.id)
        _apply(record, study)
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return _study_to_entity(record)

    async def get_study(self, study_id: uuid.UUID) -> OptimizationStudy | None:
        record = await self._session.get(OptimizationStudyRecord, study_id)
        return _study_to_entity(record) if record is not None else None

    async def list_studies(self) -> list[OptimizationStudy]:
        result = await self._session.execute(
            select(OptimizationStudyRecord).order_by(OptimizationStudyRecord.created_at.desc())
        )
        return [_study_to_entity(record) for record in result.scalars()]

    async def update_study(self, study: OptimizationStudy) -> OptimizationStudy:
        record = await self._session.get(OptimizationStudyRecord, study.id)
        if record is None:
            return await self.create_study(study)
        _apply(record, study)
        await self._session.flush()
        await self._session.refresh(record)
        return _study_to_entity(record)

    async def add_trial(self, trial: OptimizationTrial) -> None:
        self._session.add(
            OptimizationTrialRecord(
                id=trial.id,
                study_id=trial.study_id,
                number=trial.number,
                params=trial.params,
                metrics=asdict(trial.metrics),
                score=trial.score,
            )
        )
        await self._session.flush()

    async def top_trials(self, study_id: uuid.UUID, limit: int = 10) -> list[OptimizationTrial]:
        result = await self._session.execute(
            select(OptimizationTrialRecord)
            .where(OptimizationTrialRecord.study_id == study_id)
            .order_by(OptimizationTrialRecord.score.desc(), OptimizationTrialRecord.number)
            .limit(limit)
        )
        return [_trial_to_entity(record) for record in result.scalars()]
