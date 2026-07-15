"""Validation study execution: walk-forward, Monte Carlo and stress testing.

Runs inside a worker (same queue as optimizations). Every method stores its
report as a JSON-friendly dict in the ``ValidationRun`` record so the API and
dashboard can render it without extra queries.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd

from quantlab.application.event_bus import EventBus
from quantlab.application.ports import (
    BacktestEngine,
    CandleStore,
    ValidationRepository,
)
from quantlab.application.services.backtesting import MIN_BARS, DataNotAvailableError
from quantlab.application.services.optimization import OptimizerFactory, UnknownOptimizerError
from quantlab.domain.backtest import BacktestResult, CostModel
from quantlab.domain.objective import ObjectiveConfig, compute_score
from quantlab.domain.optimization import StudyStatus
from quantlab.domain.validation import (
    DEFAULT_STRESS_SCENARIOS,
    StressScenario,
    ValidationCompleted,
    ValidationFailed,
    ValidationKind,
    ValidationRun,
)
from quantlab.strategies.base import SIGNAL_COLUMNS, ParamValue
from quantlab.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)

ValidationRepositoryFactory = Callable[[], AbstractAsyncContextManager[ValidationRepository]]

MIN_TRADES_FOR_MONTE_CARLO = 10


class ValidationError(ValueError):
    """Raised when a validation cannot run with the given inputs."""


def apply_random_delay(
    signals: pd.DataFrame, max_delay_bars: int, rng: np.random.Generator
) -> pd.DataFrame:
    """Delay every signal by a random 0..max_delay bars (models slow fills)."""
    if max_delay_bars <= 0:
        return signals
    delayed = pd.DataFrame(False, index=signals.index, columns=signals.columns)
    total = len(signals)
    for column in SIGNAL_COLUMNS:
        positions = np.flatnonzero(signals[column].to_numpy())
        if len(positions) == 0:
            continue
        shifted = positions + rng.integers(0, max_delay_bars + 1, size=len(positions))
        shifted = shifted[shifted < total]
        values = np.zeros(total, dtype=bool)
        values[shifted] = True
        delayed[column] = values
    return delayed


class ValidationService:
    """Executes validation runs and persists their reports."""

    def __init__(
        self,
        store: CandleStore,
        registry: StrategyRegistry,
        engine: BacktestEngine,
        repositories: ValidationRepositoryFactory,
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

    async def run(self, run_id: uuid.UUID) -> ValidationRun:
        """Execute one validation to completion. Failures land in the record."""
        async with self._repositories() as repo:
            run = await repo.get(run_id)
        if run is None:
            raise ValidationError(f"Validation {run_id} not found")
        run.status = StudyStatus.RUNNING
        run = await self._save(run)
        logger.info(
            "Validation started: %s %s %s %s", run.kind, run.strategy_id, run.symbol, run.timeframe
        )
        try:
            data = await asyncio.to_thread(self._store.load, run.symbol, run.timeframe)
            if len(data) < MIN_BARS:
                raise DataNotAvailableError(
                    f"Only {len(data)} bars available for {run.symbol} {run.timeframe}."
                )
            run.result = await asyncio.to_thread(self._dispatch, run, data)
            run.status = StudyStatus.COMPLETED
            run.message = None
            run = await self._save(run)
            logger.info("Validation completed: %s %s", run.kind, run.strategy_id)
            await self._event_bus.publish(
                ValidationCompleted(
                    validation_id=run.id, kind=run.kind, strategy_id=run.strategy_id
                )
            )
        except Exception as exc:
            logger.exception("Validation %s failed", run_id)
            error_message = f"{type(exc).__name__}: {exc}"
            run.status = StudyStatus.FAILED
            run.message = error_message
            run = await self._save(run)
            await self._event_bus.publish(
                ValidationFailed(validation_id=run.id, kind=run.kind, error=error_message)
            )
        return run

    # -- dispatch ---------------------------------------------------------------

    def _dispatch(self, run: ValidationRun, data: pd.DataFrame) -> dict[str, Any]:
        if run.kind == ValidationKind.WALK_FORWARD:
            return self._walk_forward(run, data)
        if run.kind == ValidationKind.MONTE_CARLO:
            return self._monte_carlo(run, data)
        return self._stress(run, data)

    def _backtest(
        self,
        run: ValidationRun,
        data: pd.DataFrame,
        params: dict[str, ParamValue] | None,
        costs: CostModel | None = None,
        max_delay_bars: int = 0,
        rng: np.random.Generator | None = None,
    ) -> BacktestResult:
        strategy = self._registry.create(run.strategy_id, params)
        signals = strategy.generate_signals(data)
        if max_delay_bars > 0 and rng is not None:
            signals = apply_random_delay(signals, max_delay_bars, rng)
        orders = strategy.generate_orders(data, signals)
        return self._engine.run(data, signals, orders, costs or CostModel(), run.timeframe)

    # -- walk-forward -----------------------------------------------------------

    def _walk_forward(self, run: ValidationRun, data: pd.DataFrame) -> dict[str, Any]:
        config = run.config
        n_folds = int(config.get("n_folds", 5))
        train_ratio = float(config.get("train_ratio", 0.7))
        n_trials = int(config.get("n_trials", 30))
        optimizer_name = str(config.get("optimizer", "optuna"))
        anchored = bool(config.get("anchored", False))
        seed = config.get("seed")
        objective = ObjectiveConfig.from_dict(config.get("objective") or {})
        if optimizer_name not in self._optimizers:
            raise UnknownOptimizerError(optimizer_name)
        if not 0.5 <= train_ratio < 1.0:
            raise ValidationError("train_ratio must be in [0.5, 1.0)")

        ratio = train_ratio / (1.0 - train_ratio)
        test_len = int(len(data) / (ratio + n_folds))
        train_len = int(test_len * ratio)
        if test_len < MIN_BARS:
            raise ValidationError(
                f"Not enough data for {n_folds} folds: each test window would have "
                f"only {test_len} bars."
            )

        space = self._registry.get(run.strategy_id).metadata().parameters
        folds: list[dict[str, Any]] = []
        oos_scores: list[float] = []
        is_scores: list[float] = []
        oos_compound = 1.0
        oos_trades = 0

        for fold in range(n_folds):
            train_start = 0 if anchored else fold * test_len
            train_end = train_len + fold * test_len
            test_end = train_end + test_len
            train_data = data.iloc[train_start:train_end]
            test_data = data.iloc[train_end:test_end]

            def evaluate(params: dict[str, ParamValue], _train: pd.DataFrame = train_data) -> float:
                try:
                    result = self._backtest(run, _train, params)
                    return compute_score(result.metrics, objective)
                except Exception:
                    logger.exception("Walk-forward trial failed; penalizing")
                    return -1.0

            optimizer = self._optimizers[optimizer_name]()
            fold_seed = int(seed) + fold if seed is not None else None
            outcome = optimizer.optimize(space, evaluate, n_trials, fold_seed)

            is_result = self._backtest(run, train_data, outcome.best_params)
            oos_result = self._backtest(run, test_data, outcome.best_params)
            is_score = compute_score(is_result.metrics, objective)
            oos_score = compute_score(oos_result.metrics, objective)
            is_scores.append(is_score)
            oos_scores.append(oos_score)
            oos_compound *= 1.0 + oos_result.metrics.total_return
            oos_trades += oos_result.metrics.trades
            folds.append(
                {
                    "fold": fold + 1,
                    "train_start": str(train_data.index[0]),
                    "train_end": str(train_data.index[-1]),
                    "test_start": str(test_data.index[0]),
                    "test_end": str(test_data.index[-1]),
                    "best_params": dict(outcome.best_params),
                    "is_score": is_score,
                    "oos_score": oos_score,
                    "is_metrics": asdict(is_result.metrics),
                    "oos_metrics": asdict(oos_result.metrics),
                }
            )

        mean_is = float(np.mean(is_scores))
        mean_oos = float(np.mean(oos_scores))
        efficiency = mean_oos / mean_is if mean_is > 0 else 0.0
        return {
            "kind": "walk_forward",
            "n_folds": n_folds,
            "train_ratio": train_ratio,
            "anchored": anchored,
            "optimizer": optimizer_name,
            "n_trials": n_trials,
            "folds": folds,
            "mean_is_score": mean_is,
            "mean_oos_score": mean_oos,
            "wf_efficiency": float(efficiency),
            "oos_total_return": float(oos_compound - 1.0),
            "oos_trades": oos_trades,
            "positive_oos_folds": sum(1 for score in oos_scores if score > 0),
        }

    # -- Monte Carlo ------------------------------------------------------------

    def _monte_carlo(self, run: ValidationRun, data: pd.DataFrame) -> dict[str, Any]:
        config = run.config
        n_runs = int(config.get("n_runs", 1000))
        method = str(config.get("method", "resample"))
        seed = config.get("seed")
        if method not in ("resample", "shuffle"):
            raise ValidationError("method must be 'resample' or 'shuffle'")

        base = self._backtest(run, data, run.params)
        returns = np.asarray(base.trade_returns, dtype=float)
        if len(returns) < MIN_TRADES_FOR_MONTE_CARLO:
            raise ValidationError(
                f"Monte Carlo needs at least {MIN_TRADES_FOR_MONTE_CARLO} trades; "
                f"the base backtest produced {len(returns)}."
            )

        rng = np.random.default_rng(int(seed) if seed is not None else None)
        n_trades = len(returns)
        final_returns = np.empty(n_runs)
        max_drawdowns = np.empty(n_runs)
        for i in range(n_runs):
            sample = (
                rng.choice(returns, size=n_trades, replace=True)
                if method == "resample"
                else rng.permutation(returns)
            )
            equity = np.cumprod(1.0 + sample)
            final_returns[i] = equity[-1] - 1.0
            peak = np.maximum.accumulate(equity)
            max_drawdowns[i] = float(np.max(1.0 - equity / peak))

        def pct(values: np.ndarray, q: float) -> float:
            return float(np.percentile(values, q))

        return {
            "kind": "monte_carlo",
            "method": method,
            "n_runs": n_runs,
            "n_trades": n_trades,
            "base_metrics": asdict(base.metrics),
            "final_return_p5": pct(final_returns, 5),
            "final_return_p50": pct(final_returns, 50),
            "final_return_p95": pct(final_returns, 95),
            "max_drawdown_p50": pct(max_drawdowns, 50),
            "max_drawdown_p95": pct(max_drawdowns, 95),
            "prob_loss": float(np.mean(final_returns < 0.0)),
            "prob_ruin": float(np.mean(max_drawdowns > 0.5)),
        }

    # -- stress testing ---------------------------------------------------------

    def _stress(self, run: ValidationRun, data: pd.DataFrame) -> dict[str, Any]:
        seed = run.config.get("seed")
        rng = np.random.default_rng(int(seed) if seed is not None else 42)
        scenarios: list[dict[str, Any]] = []
        baseline_return: float | None = None
        for scenario in self._scenarios(run.config):
            costs = CostModel(
                commission_pct=scenario.commission_pct,
                slippage_pct=scenario.slippage_pct,
                spread_mult=scenario.spread_mult,
            )
            result = self._backtest(
                run,
                data,
                run.params,
                costs=costs,
                max_delay_bars=scenario.max_delay_bars,
                rng=rng,
            )
            metrics = result.metrics
            if baseline_return is None:
                baseline_return = metrics.total_return
            degradation = (
                (metrics.total_return - baseline_return) / abs(baseline_return)
                if baseline_return
                else 0.0
            )
            scenarios.append(
                {
                    "name": scenario.name,
                    "spread_mult": scenario.spread_mult,
                    "commission_pct": scenario.commission_pct,
                    "slippage_pct": scenario.slippage_pct,
                    "max_delay_bars": scenario.max_delay_bars,
                    "metrics": asdict(metrics),
                    "return_degradation": float(degradation),
                }
            )
        survived = sum(
            1 for s in scenarios[1:] if s["metrics"]["total_return"] > 0  # baseline excluded
        )
        return {
            "kind": "stress",
            "scenarios": scenarios,
            "profitable_scenarios": survived,
            "total_scenarios": len(scenarios) - 1,
        }

    @staticmethod
    def _scenarios(config: dict[str, Any]) -> tuple[StressScenario, ...]:
        raw = config.get("scenarios")
        if not raw:
            return DEFAULT_STRESS_SCENARIOS
        custom = tuple(
            StressScenario(
                name=str(item["name"]),
                spread_mult=float(item.get("spread_mult", 1.0)),
                commission_pct=float(item.get("commission_pct", 0.0)),
                slippage_pct=float(item.get("slippage_pct", 0.0)),
                max_delay_bars=int(item.get("max_delay_bars", 0)),
            )
            for item in raw
        )
        baseline = (StressScenario(name="baseline"),)
        return baseline + tuple(s for s in custom if s.name != "baseline")

    async def _save(self, run: ValidationRun) -> ValidationRun:
        async with self._repositories() as repo:
            return await repo.update(run)
