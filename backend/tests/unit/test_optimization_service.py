"""Tests for the optimization study executor (fake optimizer + fake engine)."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
import pytest

from quantlab.application.event_bus import InMemoryEventBus
from quantlab.application.ports import (
    BacktestEngine,
    Evaluator,
    OptimizationOutcome,
    OptimizationRepository,
    Optimizer,
)
from quantlab.application.services.optimization import OptimizationService, StudyNotFoundError
from quantlab.domain.backtest import BacktestMetrics, BacktestResult, CostModel, OrderPlan
from quantlab.domain.events import DomainEvent
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.objective import ObjectiveConfig
from quantlab.domain.optimization import (
    OptimizationStudy,
    OptimizationTrial,
    StudyCompleted,
    StudyFailed,
    StudyStatus,
)
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from quantlab.strategies.base import ParameterSpec, ParamValue
from quantlab.strategies.registry import StrategyRegistry
from tests.factories import make_market_data


class InMemoryOptimizationRepo(OptimizationRepository):
    def __init__(self, studies: dict[uuid.UUID, OptimizationStudy], trials: list) -> None:
        self._studies = studies
        self.trials = trials

    async def create_study(self, study: OptimizationStudy) -> OptimizationStudy:
        self._studies[study.id] = study
        return study

    async def get_study(self, study_id: uuid.UUID) -> OptimizationStudy | None:
        return self._studies.get(study_id)

    async def list_studies(self) -> list[OptimizationStudy]:
        return list(self._studies.values())

    async def update_study(self, study: OptimizationStudy) -> OptimizationStudy:
        self._studies[study.id] = study
        return study

    async def add_trial(self, trial: OptimizationTrial) -> None:
        self.trials.append(trial)

    async def top_trials(self, study_id: uuid.UUID, limit: int = 10) -> list[OptimizationTrial]:
        matching = [t for t in self.trials if t.study_id == study_id]
        return sorted(matching, key=lambda t: t.score, reverse=True)[:limit]

    async def global_ranking(
        self, limit: int = 20
    ) -> list[tuple[OptimizationTrial, OptimizationStudy]]:
        ranked = sorted(self.trials, key=lambda t: t.score, reverse=True)[:limit]
        return [(t, self._studies[t.study_id]) for t in ranked if t.study_id in self._studies]

    async def heatmap(self) -> list[tuple[str, str, float, int]]:
        cells: dict[tuple[str, str], tuple[float, int]] = {}
        for study in self._studies.values():
            if study.best_score is None:
                continue
            key = (study.symbol.value, study.timeframe.value)
            best, count = cells.get(key, (float("-inf"), 0))
            cells[key] = (max(best, study.best_score), count + 1)
        return [(s, tf, best, count) for (s, tf), (best, count) in cells.items()]


class FakeOptimizer(Optimizer):
    """Proposes ema_cross params with increasing fast periods."""

    @property
    def name(self) -> str:
        return "fake"

    def optimize(
        self,
        space: tuple[ParameterSpec, ...],
        evaluate: Evaluator,
        n_trials: int,
        seed: int | None = None,
    ) -> OptimizationOutcome:
        best_score, best_params = float("-inf"), {}
        for i in range(n_trials):
            params: dict[str, ParamValue] = {"fast_period": 5 + i, "slow_period": 100}
            score = evaluate(params)
            if score > best_score:
                best_score, best_params = score, params
        return OptimizationOutcome(
            best_params=best_params, best_score=best_score, trials_completed=n_trials
        )


class ScoreByFastPeriod(BacktestEngine):
    """Deterministic engine: more trades and sharpe for higher fast_period."""

    def run(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        orders: OrderPlan,
        costs: CostModel,
        timeframe: Timeframe,
        initial_cash: float | None = None,
    ) -> BacktestResult:
        return BacktestResult(
            metrics=BacktestMetrics(sharpe=1.0, trades=100, profit_factor=1.5),
            equity=pd.Series([1.0, 2.0], index=data.index[:2]),
        )


def build_service(
    tmp_path: Path, engine: BacktestEngine | None = None
) -> tuple[OptimizationService, dict[uuid.UUID, OptimizationStudy], list, list[DomainEvent]]:
    studies: dict[uuid.UUID, OptimizationStudy] = {}
    trials: list[OptimizationTrial] = []

    @asynccontextmanager
    async def repositories() -> AsyncIterator[OptimizationRepository]:
        yield InMemoryOptimizationRepo(studies, trials)

    bus = InMemoryEventBus()
    events: list[DomainEvent] = []

    async def record(event: DomainEvent) -> None:
        events.append(event)

    bus.subscribe(DomainEvent, record)
    store = ParquetCandleStore(tmp_path / "candles")
    store.append(Symbol.EURUSD, Timeframe.H1, make_market_data(300))
    service = OptimizationService(
        store=store,
        registry=StrategyRegistry().discover(),
        engine=engine or ScoreByFastPeriod(),
        repositories=repositories,
        event_bus=bus,
        optimizers={"fake": FakeOptimizer},
    )
    return service, studies, trials, events


def make_study(**overrides: object) -> OptimizationStudy:
    defaults: dict[str, object] = {
        "strategy_id": "ema_cross",
        "symbol": Symbol.EURUSD,
        "timeframe": Timeframe.H1,
        "optimizer": "fake",
        "n_trials": 5,
        "objective": ObjectiveConfig(min_trades=10),
    }
    defaults.update(overrides)
    return OptimizationStudy(**defaults)  # type: ignore[arg-type]


async def test_run_study_completes_and_persists_trials(tmp_path: Path) -> None:
    service, studies, trials, events = build_service(tmp_path)
    study = make_study()
    studies[study.id] = study

    result = await service.run_study(study.id)

    assert result.status == StudyStatus.COMPLETED
    assert result.trials_completed == 5
    assert result.best_score is not None and result.best_score > 0
    assert result.best_params is not None and "fast_period" in result.best_params
    assert len(trials) == 5
    assert [t.number for t in trials] == [1, 2, 3, 4, 5]
    assert all(t.study_id == study.id for t in trials)
    completed = [e for e in events if isinstance(e, StudyCompleted)]
    assert len(completed) == 1 and completed[0].trials == 5


async def test_failing_trials_are_penalized_not_fatal(tmp_path: Path) -> None:
    class ExplodingEngine(BacktestEngine):
        def run(self, data, signals, orders, costs, timeframe):  # type: ignore[no-untyped-def]
            raise RuntimeError("engine blew up")

    service, studies, trials, _ = build_service(tmp_path, engine=ExplodingEngine())
    study = make_study()
    studies[study.id] = study
    result = await service.run_study(study.id)
    assert result.status == StudyStatus.COMPLETED  # study survives broken trials
    assert result.best_score == -1.0  # every trial penalized
    assert len(trials) == 5


async def test_missing_data_fails_the_study(tmp_path: Path) -> None:
    service, studies, _, events = build_service(tmp_path)
    study = make_study(symbol=Symbol.GBPUSD)  # not in the store
    studies[study.id] = study
    result = await service.run_study(study.id)
    assert result.status == StudyStatus.FAILED
    assert result.message is not None
    assert any(isinstance(e, StudyFailed) for e in events)


async def test_unknown_optimizer_fails_the_study(tmp_path: Path) -> None:
    service, studies, _, _ = build_service(tmp_path)
    study = make_study(optimizer="nope")
    studies[study.id] = study
    result = await service.run_study(study.id)
    assert result.status == StudyStatus.FAILED
    assert "nope" in (result.message or "")


async def test_unknown_study_raises(tmp_path: Path) -> None:
    service, _, _, _ = build_service(tmp_path)
    with pytest.raises(StudyNotFoundError):
        await service.run_study(uuid.uuid4())


async def test_progress_is_updated_during_the_run(tmp_path: Path) -> None:
    service, studies, _, _ = build_service(tmp_path)
    study = make_study()
    studies[study.id] = study
    await service.run_study(study.id)
    stored = studies[study.id]
    assert stored.trials_completed == 5
    assert stored.best_score is not None


def test_optimizer_names_are_sorted(tmp_path: Path) -> None:
    service, _, _, _ = build_service(tmp_path)
    assert service.optimizer_names == ["fake"]
