"""Tests for the validation service: walk-forward, Monte Carlo, stress."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quantlab.application.event_bus import InMemoryEventBus
from quantlab.application.ports import (
    BacktestEngine,
    Evaluator,
    OptimizationOutcome,
    Optimizer,
    ValidationRepository,
)
from quantlab.application.services.validation import (
    ValidationError,
    ValidationService,
    apply_random_delay,
)
from quantlab.domain.backtest import BacktestMetrics, BacktestResult, CostModel, OrderPlan
from quantlab.domain.events import DomainEvent
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.optimization import StudyStatus
from quantlab.domain.validation import (
    ValidationCompleted,
    ValidationFailed,
    ValidationKind,
    ValidationRun,
)
from quantlab.infrastructure.data.parquet_store import ParquetCandleStore
from quantlab.strategies.base import ParameterSpec, ParamValue
from quantlab.strategies.registry import StrategyRegistry
from tests.factories import make_market_data


class InMemoryValidationRepo(ValidationRepository):
    def __init__(self, runs: dict[uuid.UUID, ValidationRun]) -> None:
        self._runs = runs

    async def create(self, run: ValidationRun) -> ValidationRun:
        self._runs[run.id] = run
        return run

    async def get(self, run_id: uuid.UUID) -> ValidationRun | None:
        return self._runs.get(run_id)

    async def list_all(self) -> list[ValidationRun]:
        return list(self._runs.values())

    async def update(self, run: ValidationRun) -> ValidationRun:
        self._runs[run.id] = run
        return run


class DeterministicEngine(BacktestEngine):
    """Returns for each run: costs-sensitive metrics and fixed trade returns."""

    def __init__(self) -> None:
        self.calls: list[CostModel] = []

    def run(
        self,
        data: pd.DataFrame,
        signals: pd.DataFrame,
        orders: OrderPlan,
        costs: CostModel,
        timeframe: Timeframe,
    ) -> BacktestResult:
        self.calls.append(costs)
        # Costs degrade the outcome so stress scenarios rank below baseline.
        friction = (
            costs.commission_pct * 1000
            + costs.slippage_pct * 1000
            + (costs.spread_mult - 1.0) * 0.1
        )
        total_return = max(0.5 - friction, -0.5)
        trade_returns = list(np.full(20, 0.02)) + [-0.01] * 5
        return BacktestResult(
            metrics=BacktestMetrics(
                total_return=total_return,
                sharpe=1.5 - friction,
                profit_factor=1.8,
                trades=40,  # above the default objective's min_trades gate
                max_drawdown=0.1,
                win_rate=0.8,
            ),
            equity=pd.Series([1.0, 1.0 + total_return], index=data.index[:2]),
            trade_returns=trade_returns,
        )


class FixedOptimizer(Optimizer):
    """Always proposes the same params; counts invocations."""

    def __init__(self) -> None:
        self.runs = 0

    @property
    def name(self) -> str:
        return "fixed"

    def optimize(
        self,
        space: tuple[ParameterSpec, ...],
        evaluate: Evaluator,
        n_trials: int,
        seed: int | None = None,
    ) -> OptimizationOutcome:
        self.runs += 1
        params: dict[str, ParamValue] = {"fast_period": 10, "slow_period": 50}
        score = evaluate(params)
        return OptimizationOutcome(best_params=params, best_score=score, trials_completed=n_trials)


def build_service(
    tmp_path: Path,
    engine: BacktestEngine | None = None,
    bars: int = 1200,
) -> tuple[ValidationService, dict[uuid.UUID, ValidationRun], list[DomainEvent], FixedOptimizer]:
    runs: dict[uuid.UUID, ValidationRun] = {}

    @asynccontextmanager
    async def repositories() -> AsyncIterator[ValidationRepository]:
        yield InMemoryValidationRepo(runs)

    bus = InMemoryEventBus()
    events: list[DomainEvent] = []

    async def record(event: DomainEvent) -> None:
        events.append(event)

    bus.subscribe(DomainEvent, record)
    store = ParquetCandleStore(tmp_path / "candles")
    store.append(Symbol.EURUSD, Timeframe.H1, make_market_data(bars))
    optimizer = FixedOptimizer()
    service = ValidationService(
        store=store,
        registry=StrategyRegistry().discover(),
        engine=engine or DeterministicEngine(),
        repositories=repositories,
        event_bus=bus,
        optimizers={"fixed": lambda: optimizer},
    )
    return service, runs, events, optimizer


def make_run(kind: ValidationKind, **overrides: object) -> ValidationRun:
    defaults: dict[str, object] = {
        "kind": kind,
        "strategy_id": "ema_cross",
        "symbol": Symbol.EURUSD,
        "timeframe": Timeframe.H1,
    }
    defaults.update(overrides)
    return ValidationRun(**defaults)  # type: ignore[arg-type]


# -- walk-forward ---------------------------------------------------------------


async def test_walk_forward_optimizes_each_fold_and_reports(tmp_path: Path) -> None:
    service, runs, events, optimizer = build_service(tmp_path)
    run = make_run(
        ValidationKind.WALK_FORWARD,
        config={"n_folds": 3, "train_ratio": 0.7, "n_trials": 5, "optimizer": "fixed", "seed": 1},
    )
    runs[run.id] = run

    result = await service.run(run.id)

    assert result.status == StudyStatus.COMPLETED
    assert result.result is not None
    report = result.result
    assert optimizer.runs == 3  # one optimization per fold
    assert len(report["folds"]) == 3
    assert report["wf_efficiency"] > 0
    assert report["positive_oos_folds"] == 3
    for fold in report["folds"]:
        assert fold["best_params"]["fast_period"] == 10
        assert fold["oos_metrics"]["trades"] == 40
    assert any(isinstance(e, ValidationCompleted) for e in events)


async def test_walk_forward_folds_do_not_overlap_train_and_test(tmp_path: Path) -> None:
    service, runs, _, _ = build_service(tmp_path)
    run = make_run(
        ValidationKind.WALK_FORWARD,
        config={"n_folds": 3, "train_ratio": 0.7, "n_trials": 2, "optimizer": "fixed"},
    )
    runs[run.id] = run
    result = await service.run(run.id)
    assert result.result is not None
    for fold in result.result["folds"]:
        assert fold["train_end"] < fold["test_start"]  # OOS strictly after IS


async def test_walk_forward_rejects_too_many_folds(tmp_path: Path) -> None:
    service, runs, events, _ = build_service(tmp_path, bars=300)
    run = make_run(
        ValidationKind.WALK_FORWARD,
        config={"n_folds": 10, "train_ratio": 0.8, "optimizer": "fixed"},
    )
    runs[run.id] = run
    result = await service.run(run.id)
    assert result.status == StudyStatus.FAILED
    assert "Not enough data" in (result.message or "")
    assert any(isinstance(e, ValidationFailed) for e in events)


async def test_walk_forward_unknown_optimizer_fails(tmp_path: Path) -> None:
    service, runs, _, _ = build_service(tmp_path)
    run = make_run(ValidationKind.WALK_FORWARD, config={"optimizer": "nope"})
    runs[run.id] = run
    result = await service.run(run.id)
    assert result.status == StudyStatus.FAILED


# -- Monte Carlo ------------------------------------------------------------------


async def test_monte_carlo_reports_distributions(tmp_path: Path) -> None:
    service, runs, _, _ = build_service(tmp_path)
    run = make_run(ValidationKind.MONTE_CARLO, config={"n_runs": 200, "seed": 7})
    runs[run.id] = run

    result = await service.run(run.id)

    assert result.status == StudyStatus.COMPLETED
    assert result.result is not None
    report = result.result
    assert report["n_runs"] == 200
    assert report["n_trades"] == 25
    assert report["final_return_p5"] <= report["final_return_p50"] <= report["final_return_p95"]
    assert 0.0 <= report["prob_loss"] <= 1.0
    assert report["max_drawdown_p95"] >= report["max_drawdown_p50"] >= 0.0


async def test_monte_carlo_is_deterministic_with_seed(tmp_path: Path) -> None:
    service, runs, _, _ = build_service(tmp_path)
    first = make_run(ValidationKind.MONTE_CARLO, config={"n_runs": 100, "seed": 42})
    second = make_run(ValidationKind.MONTE_CARLO, config={"n_runs": 100, "seed": 42})
    runs[first.id] = first
    runs[second.id] = second
    a = await service.run(first.id)
    b = await service.run(second.id)
    assert a.result is not None and b.result is not None
    assert a.result["final_return_p50"] == b.result["final_return_p50"]


async def test_monte_carlo_shuffle_keeps_final_return_fixed(tmp_path: Path) -> None:
    """Permutation reorders trades: drawdowns vary but the compounded end is identical."""
    service, runs, _, _ = build_service(tmp_path)
    run = make_run(ValidationKind.MONTE_CARLO, config={"n_runs": 50, "method": "shuffle"})
    runs[run.id] = run
    result = await service.run(run.id)
    assert result.result is not None
    assert result.result["final_return_p5"] == pytest.approx(result.result["final_return_p95"])


async def test_monte_carlo_needs_enough_trades(tmp_path: Path) -> None:
    class FewTradesEngine(DeterministicEngine):
        def run(self, data, signals, orders, costs, timeframe):  # type: ignore[no-untyped-def]
            result = super().run(data, signals, orders, costs, timeframe)
            result.trade_returns = [0.01, 0.02]
            return result

    service, runs, _, _ = build_service(tmp_path, engine=FewTradesEngine())
    run = make_run(ValidationKind.MONTE_CARLO)
    runs[run.id] = run
    result = await service.run(run.id)
    assert result.status == StudyStatus.FAILED
    assert "at least" in (result.message or "")


async def test_monte_carlo_rejects_unknown_method(tmp_path: Path) -> None:
    service, runs, _, _ = build_service(tmp_path)
    run = make_run(ValidationKind.MONTE_CARLO, config={"method": "bogus"})
    runs[run.id] = run
    result = await service.run(run.id)
    assert result.status == StudyStatus.FAILED


# -- stress -----------------------------------------------------------------------


async def test_stress_runs_default_scenarios_and_measures_degradation(tmp_path: Path) -> None:
    engine = DeterministicEngine()
    service, runs, _, _ = build_service(tmp_path, engine=engine)
    run = make_run(ValidationKind.STRESS, config={"seed": 1})
    runs[run.id] = run

    result = await service.run(run.id)

    assert result.status == StudyStatus.COMPLETED
    assert result.result is not None
    report = result.result
    names = [s["name"] for s in report["scenarios"]]
    assert names[0] == "baseline"
    assert "spread_x3" in names and "random_delay_3" in names and "hostile_combo" in names
    baseline = report["scenarios"][0]
    hostile = next(s for s in report["scenarios"] if s["name"] == "hostile_combo")
    assert hostile["metrics"]["total_return"] < baseline["metrics"]["total_return"]
    assert hostile["return_degradation"] < 0
    assert report["total_scenarios"] == len(names) - 1
    # engine received the scaled costs
    spread_x3_costs = engine.calls[2]
    assert spread_x3_costs.spread_mult == 3.0


async def test_stress_supports_custom_scenarios(tmp_path: Path) -> None:
    service, runs, _, _ = build_service(tmp_path)
    run = make_run(
        ValidationKind.STRESS,
        config={"scenarios": [{"name": "wide_spread", "spread_mult": 5.0}]},
    )
    runs[run.id] = run
    result = await service.run(run.id)
    assert result.result is not None
    assert [s["name"] for s in result.result["scenarios"]] == ["baseline", "wide_spread"]


# -- helpers ------------------------------------------------------------------------


def test_apply_random_delay_moves_signals_forward_only() -> None:
    data = make_market_data(100)
    signals = pd.DataFrame(
        False,
        index=data.index,
        columns=["long_entry", "long_exit", "short_entry", "short_exit"],
    )
    signals.iloc[10, 0] = True
    signals.iloc[50, 0] = True
    rng = np.random.default_rng(3)
    delayed = apply_random_delay(signals, max_delay_bars=3, rng=rng)
    positions = np.flatnonzero(delayed["long_entry"].to_numpy())
    assert len(positions) == 2
    assert 10 <= positions[0] <= 13
    assert 50 <= positions[1] <= 53
    # zero delay is a no-op
    assert apply_random_delay(signals, 0, rng) is signals


async def test_unknown_run_raises(tmp_path: Path) -> None:
    service, _, _, _ = build_service(tmp_path)
    with pytest.raises(ValidationError):
        await service.run(uuid.uuid4())
