"""Optuna (TPE / Bayesian) implementation of the ``Optimizer`` port."""

import optuna

from quantlab.application.ports import Evaluator, OptimizationOutcome, Optimizer
from quantlab.strategies.base import ParameterSpec, ParamValue

optuna.logging.set_verbosity(optuna.logging.WARNING)


def _suggest(trial: optuna.Trial, spec: ParameterSpec) -> ParamValue:
    if spec.kind == "int":
        return trial.suggest_int(
            spec.name, int(spec.low or 0), int(spec.high or 0), step=int(spec.step or 1)
        )
    if spec.kind == "float":
        return trial.suggest_float(spec.name, float(spec.low or 0.0), float(spec.high or 0.0))
    if spec.kind == "bool":
        return bool(trial.suggest_categorical(spec.name, [False, True]))
    return str(trial.suggest_categorical(spec.name, list(spec.choices or ())))


class OptunaOptimizer(Optimizer):
    """Tree-structured Parzen Estimator sampler over the strategy's parameter space."""

    @property
    def name(self) -> str:
        return "optuna"

    def optimize(
        self,
        space: tuple[ParameterSpec, ...],
        evaluate: Evaluator,
        n_trials: int,
        seed: int | None = None,
    ) -> OptimizationOutcome:
        study = optuna.create_study(
            direction="maximize",
            # Parameters such as fast/slow EMA, SL/TP and enabled filters are
            # correlated.  Multivariate TPE models those dependencies instead
            # of exploring each dimension in isolation.
            sampler=optuna.samplers.TPESampler(seed=seed, multivariate=True, group=True),
        )

        def objective(trial: optuna.Trial) -> float:
            params = {spec.name: _suggest(trial, spec) for spec in space}
            return evaluate(params)

        study.optimize(objective, n_trials=n_trials)
        return OptimizationOutcome(
            best_params=dict(study.best_params),
            best_score=float(study.best_value),
            trials_completed=len(study.trials),
        )
