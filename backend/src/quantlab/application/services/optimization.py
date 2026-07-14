"""Optimization study execution.

Runs inside a worker process: loads the dataset once, then lets the configured
optimizer propose parameter sets; each proposal is backtested and scored with
the study's objective. Every trial is persisted as it completes so the
dashboard can show live progress and rankings.

The CPU-bound search loop runs in a thread; per-trial persistence hops back to
the event loop via ``run_coroutine_threadsafe`` (awaited, so progress in the
database never lags more than one trial behind).
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

import pandas as pd

from quantlab.application.event_bus import EventBus
from quantlab.application.ports import (
    BacktestEngine,
    CandleStore,
    OptimizationRepository,
    Optimizer,
)
from quantlab.application.services.backtesting import MIN_BARS, DataNotAvailableError
from quantlab.domain.backtest import BacktestMetrics, CostModel
from quantlab.domain.objective import PENALTY_SCORE, compute_score
from quantlab.domain.optimization import (
    OptimizationStudy,
    OptimizationTrial,
    StudyCompleted,
    StudyFailed,
    StudyStatus,
)
from quantlab.strategies.base import ParamValue
from quantlab.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)

OptimizationRepositoryFactory = Callable[[], AbstractAsyncContextManager[OptimizationRepository]]
OptimizerFactory = Callable[[], Optimizer]


class UnknownOptimizerError(KeyError):
    """Raised when a study references an optimizer that is not registered."""


class StudyNotFoundError(LookupError):
    """Raised when the requested study does not exist."""


class OptimizationService:
    """Executes optimization studies and persists their progress."""

    def __init__(
        self,
        store: CandleStore,
        registry: StrategyRegistry,
        engine: BacktestEngine,
        repositories: OptimizationRepositoryFactory,
        event_bus: EventBus,
        optimizers: dict[str, OptimizerFactory],
    ) -> None:
        self._store = store
        self._registry = registry
        self._engine = engine
        self._repositories = repositories
        self._event_bus = event_bus
        self._optimizers = optimizers

    @property
    def optimizer_names(self) -> list[str]:
        return sorted(self._optimizers)

    async def run_study(self, study_id: uuid.UUID) -> OptimizationStudy:
        """Execute one study to completion. Failures land in the study record."""
        async with self._repositories() as repo:
            study = await repo.get_study(study_id)
        if study is None:
            raise StudyNotFoundError(str(study_id))
        study.status = StudyStatus.RUNNING
        study = await self._save(study)
        try:
            return await self._execute(study)
        except Exception as exc:
            logger.exception("Study %s failed", study_id)
            error_message = f"{type(exc).__name__}: {exc}"
            study.status = StudyStatus.FAILED
            study.message = error_message
            study = await self._save(study)
            await self._event_bus.publish(
                StudyFailed(study_id=study.id, strategy_id=study.strategy_id, error=error_message)
            )
            return study

    async def _execute(self, study: OptimizationStudy) -> OptimizationStudy:
        if study.optimizer not in self._optimizers:
            raise UnknownOptimizerError(study.optimizer)
        data = await asyncio.to_thread(
            self._store.load, study.symbol, study.timeframe, study.range_start, study.range_end
        )
        if len(data) < MIN_BARS:
            raise DataNotAvailableError(
                f"Only {len(data)} bars available for {study.symbol} {study.timeframe}."
            )
        space = self._registry.get(study.strategy_id).metadata().parameters
        optimizer = self._optimizers[study.optimizer]()
        loop = asyncio.get_running_loop()
        evaluate = self._build_evaluator(study, data, loop)

        outcome = await asyncio.to_thread(
            optimizer.optimize, space, evaluate, study.n_trials, study.seed
        )

        study.status = StudyStatus.COMPLETED
        study.best_score = outcome.best_score
        study.best_params = dict(outcome.best_params)
        study.trials_completed = outcome.trials_completed
        study.message = None
        study = await self._save(study)
        await self._event_bus.publish(
            StudyCompleted(
                study_id=study.id,
                strategy_id=study.strategy_id,
                best_score=outcome.best_score,
                trials=outcome.trials_completed,
            )
        )
        return study

    def _build_evaluator(
        self, study: OptimizationStudy, data: pd.DataFrame, loop: asyncio.AbstractEventLoop
    ) -> Callable[[dict[str, ParamValue]], float]:
        """Score one parameter set; called by the optimizer from a worker thread."""
        counter = {"number": 0}

        def evaluate(params: dict[str, ParamValue]) -> float:
            counter["number"] += 1
            try:
                strategy = self._registry.create(study.strategy_id, params)
                signals = strategy.generate_signals(data)
                orders = strategy.generate_orders(data, signals)
                result = self._engine.run(data, signals, orders, CostModel(), study.timeframe)
                metrics = result.metrics
                score = compute_score(metrics, study.objective)
            except Exception:
                logger.exception(
                    "Trial %s of study %s failed; penalizing", counter["number"], study.id
                )
                metrics = BacktestMetrics()
                score = PENALTY_SCORE
            trial = OptimizationTrial(
                study_id=study.id,
                number=counter["number"],
                params=dict(params),
                score=score,
                metrics=metrics,
            )
            asyncio.run_coroutine_threadsafe(self._record_trial(study, trial), loop).result()
            return score

        return evaluate

    async def _record_trial(self, study: OptimizationStudy, trial: OptimizationTrial) -> None:
        study.trials_completed = trial.number
        if study.best_score is None or trial.score > study.best_score:
            study.best_score = trial.score
            study.best_params = dict(trial.params)
        async with self._repositories() as repo:
            await repo.add_trial(trial)
            await repo.update_study(study)

    async def _save(self, study: OptimizationStudy) -> OptimizationStudy:
        async with self._repositories() as repo:
            return await repo.update_study(study)
