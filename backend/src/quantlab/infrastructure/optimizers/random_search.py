"""Uniform random search: dependency-free baseline for the ``Optimizer`` port."""

import random

from quantlab.application.ports import Evaluator, OptimizationOutcome, Optimizer
from quantlab.strategies.base import ParameterSpec, ParamValue


def _sample(rng: random.Random, spec: ParameterSpec) -> ParamValue:
    if spec.kind == "int":
        step = int(spec.step or 1)
        low, high = int(spec.low or 0), int(spec.high or 0)
        return low + rng.randrange(0, (high - low) // step + 1) * step
    if spec.kind == "float":
        return rng.uniform(float(spec.low or 0.0), float(spec.high or 0.0))
    if spec.kind == "bool":
        return rng.random() < 0.5
    return rng.choice(list(spec.choices or ()))


class RandomSearchOptimizer(Optimizer):
    """Samples the space uniformly; a sanity baseline any smarter search must beat."""

    @property
    def name(self) -> str:
        return "random"

    def optimize(
        self,
        space: tuple[ParameterSpec, ...],
        evaluate: Evaluator,
        n_trials: int,
        seed: int | None = None,
    ) -> OptimizationOutcome:
        rng = random.Random(seed)
        best_params: dict[str, ParamValue] = {}
        best_score = float("-inf")
        for _ in range(n_trials):
            params = {spec.name: _sample(rng, spec) for spec in space}
            score = evaluate(params)
            if score > best_score:
                best_score, best_params = score, params
        return OptimizationOutcome(
            best_params=best_params, best_score=best_score, trials_completed=n_trials
        )
