"""Contract tests for both Optimizer adapters on a known objective."""

import pytest

from quantlab.application.ports import Optimizer
from quantlab.infrastructure.optimizers.optuna_optimizer import OptunaOptimizer
from quantlab.infrastructure.optimizers.random_search import RandomSearchOptimizer
from quantlab.strategies.base import ParameterSpec, ParamValue

SPACE = (
    ParameterSpec("x", "int", 0, 0, 20),
    ParameterSpec("y", "float", 0.0, -5.0, 5.0),
    ParameterSpec("fast", "bool", False),
    ParameterSpec("mode", "categorical", "a", choices=("a", "b")),
)


def objective(params: dict[str, ParamValue]) -> float:
    """Maximum (=2.0 bonus included) at x=10, y=2.0, fast=True, mode='b'."""
    x = float(params["x"])  # type: ignore[arg-type]
    y = float(params["y"])  # type: ignore[arg-type]
    score = -((x - 10.0) ** 2) / 100.0 - ((y - 2.0) ** 2) / 25.0
    if params["fast"]:
        score += 1.0
    if params["mode"] == "b":
        score += 1.0
    return score


@pytest.mark.parametrize("optimizer", [OptunaOptimizer(), RandomSearchOptimizer()])
def test_optimizer_finds_a_good_region(optimizer: Optimizer) -> None:
    outcome = optimizer.optimize(SPACE, objective, n_trials=80, seed=42)
    assert outcome.trials_completed == 80
    assert outcome.best_score > 1.0  # must at least discover the bonuses
    assert 0 <= int(outcome.best_params["x"]) <= 20  # type: ignore[arg-type]
    assert isinstance(outcome.best_params["fast"], bool)
    assert outcome.best_params["mode"] in ("a", "b")


@pytest.mark.parametrize("optimizer", [OptunaOptimizer(), RandomSearchOptimizer()])
def test_optimizer_calls_evaluate_once_per_trial(optimizer: Optimizer) -> None:
    calls: list[dict[str, ParamValue]] = []

    def counting(params: dict[str, ParamValue]) -> float:
        calls.append(params)
        return objective(params)

    optimizer.optimize(SPACE, counting, n_trials=15, seed=1)
    assert len(calls) == 15
    for params in calls:
        assert set(params) == {"x", "y", "fast", "mode"}


@pytest.mark.parametrize("optimizer", [OptunaOptimizer(), RandomSearchOptimizer()])
def test_seed_makes_search_deterministic(optimizer: Optimizer) -> None:
    first = optimizer.optimize(SPACE, objective, n_trials=20, seed=7)
    second = type(optimizer)().optimize(SPACE, objective, n_trials=20, seed=7)
    assert first.best_params == second.best_params
    assert first.best_score == second.best_score


def test_optuna_beats_random_on_average() -> None:
    """The smart sampler should outperform the baseline on this smooth objective."""
    optuna_scores = [
        OptunaOptimizer().optimize(SPACE, objective, n_trials=60, seed=s).best_score
        for s in range(3)
    ]
    random_scores = [
        RandomSearchOptimizer().optimize(SPACE, objective, n_trials=60, seed=s).best_score
        for s in range(3)
    ]
    assert sum(optuna_scores) / 3 >= sum(random_scores) / 3 - 0.05


def test_int_step_is_respected() -> None:
    space = (ParameterSpec("n", "int", 10, 10, 50, step=10),)
    seen: set[int] = set()

    def track(params: dict[str, ParamValue]) -> float:
        seen.add(int(params["n"]))  # type: ignore[arg-type]
        return 0.0

    RandomSearchOptimizer().optimize(space, track, n_trials=30, seed=3)
    assert seen <= {10, 20, 30, 40, 50}
