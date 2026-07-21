"""Trainer adapters with a single contract.

Each trainer fits on the train split (with the validation split for early
stopping where supported) and returns a ``TrainedArtifact``: a prediction
callable (probabilities for classification, values for regression), a
persistence callable and feature importances. Heavy libraries are imported
inside each function so only the worker pays the import cost.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np

Task = Literal["classification", "regression"]
PredictFn = Callable[[np.ndarray], np.ndarray]


@dataclass
class TrainedArtifact:
    predict: PredictFn
    save: Callable[[Path], None]
    importances: dict[str, float] = field(default_factory=dict)


TrainerFn = Callable[
    [np.ndarray, np.ndarray, np.ndarray, np.ndarray, Task, dict[str, Any], list[str]],
    TrainedArtifact,
]


def _importances(names: list[str], values: Any) -> dict[str, float]:
    scores = np.asarray(values, dtype=float)
    if scores.sum() > 0:
        scores = scores / scores.sum()
    ranked = sorted(zip(names, scores, strict=False), key=lambda item: -item[1])
    return {name: round(float(score), 5) for name, score in ranked}


def train_xgboost(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_valid: np.ndarray,
    y_valid: np.ndarray,
    task: Task,
    params: dict[str, Any],
    names: list[str],
) -> TrainedArtifact:
    import joblib
    import xgboost as xgb

    common: dict[str, Any] = {
        "n_estimators": int(params.get("n_estimators", 300)),
        "max_depth": int(params.get("max_depth", 5)),
        "learning_rate": float(params.get("learning_rate", 0.05)),
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "early_stopping_rounds": 30,
        "verbosity": 0,
    }
    if task == "classification":
        model = xgb.XGBClassifier(**common, eval_metric="auc")
    else:
        model = xgb.XGBRegressor(**common, eval_metric="mae")
    model.fit(x_train, y_train, eval_set=[(x_valid, y_valid)], verbose=False)
    predict: PredictFn = (
        (lambda x: model.predict_proba(x)[:, 1]) if task == "classification" else model.predict
    )
    return TrainedArtifact(
        predict=predict,
        save=lambda path: joblib.dump(model, path),
        importances=_importances(names, model.feature_importances_),
    )


def train_lightgbm(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_valid: np.ndarray,
    y_valid: np.ndarray,
    task: Task,
    params: dict[str, Any],
    names: list[str],
) -> TrainedArtifact:
    import joblib
    import lightgbm as lgb

    common: dict[str, Any] = {
        "n_estimators": int(params.get("n_estimators", 300)),
        "max_depth": int(params.get("max_depth", -1)),
        "learning_rate": float(params.get("learning_rate", 0.05)),
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "verbosity": -1,
    }
    model = (
        lgb.LGBMClassifier(**common) if task == "classification" else lgb.LGBMRegressor(**common)
    )
    model.fit(
        x_train,
        y_train,
        eval_set=[(x_valid, y_valid)],
        callbacks=[lgb.early_stopping(30, verbose=False)],
    )
    predict: PredictFn = (
        (lambda x: model.predict_proba(x)[:, 1]) if task == "classification" else model.predict
    )
    return TrainedArtifact(
        predict=predict,
        save=lambda path: joblib.dump(model, path),
        importances=_importances(names, model.feature_importances_),
    )


def train_catboost(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_valid: np.ndarray,
    y_valid: np.ndarray,
    task: Task,
    params: dict[str, Any],
    names: list[str],
) -> TrainedArtifact:
    import joblib
    from catboost import CatBoostClassifier, CatBoostRegressor

    common: dict[str, Any] = {
        "iterations": int(params.get("n_estimators", 300)),
        "depth": int(params.get("max_depth", 6)),
        "learning_rate": float(params.get("learning_rate", 0.05)),
        "early_stopping_rounds": 30,
        "verbose": False,
        "allow_writing_files": False,
    }
    model = (
        CatBoostClassifier(**common) if task == "classification" else CatBoostRegressor(**common)
    )
    model.fit(x_train, y_train, eval_set=(x_valid, y_valid))
    predict: PredictFn = (
        (lambda x: model.predict_proba(x)[:, 1])
        if task == "classification"
        else (lambda x: np.asarray(model.predict(x), dtype=float))
    )
    return TrainedArtifact(
        predict=predict,
        save=lambda path: joblib.dump(model, path),
        importances=_importances(names, model.get_feature_importance()),
    )


def train_torch_mlp(
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_valid: np.ndarray,
    y_valid: np.ndarray,
    task: Task,
    params: dict[str, Any],
    names: list[str],
) -> TrainedArtifact:
    import torch
    from torch import nn

    torch.manual_seed(int(params.get("seed", 42)))
    hidden = int(params.get("hidden_size", 64))
    epochs = int(params.get("epochs", 30))
    device = torch.device("cpu")

    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0) + 1e-9

    def to_tensor(x: np.ndarray) -> torch.Tensor:
        return torch.tensor((x - mean) / std, dtype=torch.float32, device=device)

    model = nn.Sequential(
        nn.Linear(x_train.shape[1], hidden),
        nn.ReLU(),
        nn.Linear(hidden, hidden),
        nn.ReLU(),
        nn.Linear(hidden, 1),
    ).to(device)
    loss_fn: nn.Module = nn.BCEWithLogitsLoss() if task == "classification" else nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=float(params.get("learning_rate", 1e-3)))

    x_t, y_t = to_tensor(x_train), torch.tensor(y_train, dtype=torch.float32).unsqueeze(1)
    x_v, y_v = to_tensor(x_valid), torch.tensor(y_valid, dtype=torch.float32).unsqueeze(1)
    best_valid = float("inf")
    best_state = {k: v.clone() for k, v in model.state_dict().items()}
    for _ in range(epochs):
        model.train()
        optimizer.zero_grad()
        loss = loss_fn(model(x_t), y_t)
        loss.backward()
        optimizer.step()
        model.eval()
        with torch.no_grad():
            valid_loss = float(loss_fn(model(x_v), y_v))
        if valid_loss < best_valid:
            best_valid = valid_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    model.eval()

    def predict(x: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            logits = model(to_tensor(x)).squeeze(1).numpy()
        result = 1.0 / (1.0 + np.exp(-logits)) if task == "classification" else logits
        return np.asarray(result)

    def save(path: Path) -> None:
        torch.save({"state_dict": model.state_dict(), "mean": mean, "std": std}, path)

    return TrainedArtifact(predict=predict, save=save)


TRAINERS: dict[str, TrainerFn] = {
    "xgboost": train_xgboost,
    "lightgbm": train_lightgbm,
    "catboost": train_catboost,
    "torch_mlp": train_torch_mlp,
}
