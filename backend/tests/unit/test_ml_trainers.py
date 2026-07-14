"""Contract tests for every supervised trainer on a learnable synthetic problem."""

from pathlib import Path

import numpy as np
import pytest

from quantlab.infrastructure.ml.trainers import TRAINERS

RNG = np.random.default_rng(7)
N = 600
X = RNG.normal(size=(N, 6))
# Signal: feature 0 and 2 drive the outcome; rest is noise.
LOGIT = 2.0 * X[:, 0] - 1.5 * X[:, 2] + RNG.normal(0.0, 0.5, N)
Y_CLASS = (LOGIT > 0).astype(float)
Y_REG = LOGIT
NAMES = [f"f{i}" for i in range(6)]

TRAIN, VALID, TEST = slice(0, 400), slice(400, 500), slice(500, 600)
FAST = {"n_estimators": 40, "epochs": 60, "hidden_size": 16}


@pytest.mark.parametrize("algorithm", sorted(TRAINERS))
def test_classification_beats_chance_and_saves(algorithm: str, tmp_path: Path) -> None:
    trained = TRAINERS[algorithm](
        X[TRAIN], Y_CLASS[TRAIN], X[VALID], Y_CLASS[VALID], "classification", FAST, NAMES
    )
    probabilities = trained.predict(X[TEST])
    assert probabilities.shape == (100,)
    assert np.all((probabilities >= 0.0) & (probabilities <= 1.0))
    accuracy = float(np.mean((probabilities >= 0.5) == Y_CLASS[TEST]))
    assert accuracy > 0.7, f"{algorithm} accuracy {accuracy}"
    artifact = tmp_path / f"{algorithm}.bin"
    trained.save(artifact)
    assert artifact.exists() and artifact.stat().st_size > 0


@pytest.mark.parametrize("algorithm", sorted(TRAINERS))
def test_regression_explains_variance(algorithm: str) -> None:
    # The MLP trains full-batch: it needs more iterations than the tree models.
    params = {**FAST, "epochs": 400, "learning_rate": 0.01} if algorithm == "torch_mlp" else FAST
    trained = TRAINERS[algorithm](
        X[TRAIN], Y_REG[TRAIN], X[VALID], Y_REG[VALID], "regression", params, NAMES
    )
    predictions = trained.predict(X[TEST])
    residual = np.mean((predictions - Y_REG[TEST]) ** 2)
    variance = np.var(Y_REG[TEST])
    assert residual < variance * 0.5, f"{algorithm} explains too little variance"


def test_tree_importances_identify_informative_features() -> None:
    trained = TRAINERS["xgboost"](
        X[TRAIN], Y_CLASS[TRAIN], X[VALID], Y_CLASS[VALID], "classification", FAST, NAMES
    )
    top_two = list(trained.importances)[:2]
    assert set(top_two) == {"f0", "f2"}
