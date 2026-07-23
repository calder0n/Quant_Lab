"""ML/RL training orchestration.

Runs inside a worker. Supervised models: causal features + triple-barrier
labels, chronological train/valid/test split (never shuffled — this is a time
series), honest metrics on the untouched test tail. RL: PPO over the trading
environment, evaluated deterministically on the held-out tail.
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from quantlab.application.event_bus import EventBus
from quantlab.application.ports import CandleStore, MlModelRepository
from quantlab.application.services.backtesting import DataNotAvailableError
from quantlab.domain.ml import MlModel, ModelKind, ModelTrained, ModelTrainingFailed
from quantlab.domain.optimization import StudyStatus
from quantlab.ml.features import build_features, feature_names
from quantlab.ml.labels import (
    CLASSIFICATION_TARGETS,
    target_vector,
    triple_barrier_labels,
)

logger = logging.getLogger(__name__)

MlModelRepositoryFactory = Callable[[], AbstractAsyncContextManager[MlModelRepository]]

MIN_ROWS = 500


class MlTrainingError(ValueError):
    """Raised when a model cannot be trained with the given inputs."""


class MlService:
    """Trains and registers supervised ML models and RL policies."""

    def __init__(
        self,
        store: CandleStore,
        repositories: MlModelRepositoryFactory,
        event_bus: EventBus,
        artifacts_dir: Path,
    ) -> None:
        self._store = store
        self._repositories = repositories
        self._event_bus = event_bus
        self._artifacts_dir = artifacts_dir

    async def train(self, model_id: uuid.UUID) -> MlModel:
        """Train one registered model. Failures land in the record."""
        async with self._repositories() as repo:
            model = await repo.get(model_id)
        if model is None:
            raise MlTrainingError(f"Model {model_id} not found")
        model.status = StudyStatus.RUNNING
        model = await self._save(model)
        logger.info(
            "Training started: %s %s %s on %s %s",
            model.kind,
            model.algorithm,
            model.target,
            model.symbol,
            model.timeframe,
        )
        try:
            if model.kind == ModelKind.ML:
                metrics, artifact = await asyncio.to_thread(self._train_supervised, model)
            else:
                metrics, artifact = await asyncio.to_thread(self._train_rl, model)
            model.metrics = metrics
            model.artifact_path = str(artifact)
            model.status = StudyStatus.COMPLETED
            model.message = None
            model = await self._save(model)
            logger.info("Training completed: %s %s %s", model.kind, model.algorithm, model.target)
            await self._event_bus.publish(
                ModelTrained(model_id=model.id, kind=model.kind, algorithm=model.algorithm)
            )
        except Exception as exc:
            logger.exception("Training %s failed", model_id)
            error_message = f"{type(exc).__name__}: {exc}"
            model.status = StudyStatus.FAILED
            model.message = error_message
            model = await self._save(model)
            await self._event_bus.publish(
                ModelTrainingFailed(model_id=model.id, kind=model.kind, error=error_message)
            )
        return model

    # -- supervised ----------------------------------------------------------------

    def _prepare(self, model: MlModel) -> pd.DataFrame:
        data = self._store.load(model.symbol, model.timeframe)
        max_rows = int(model.config.get("max_rows", 100_000))
        if len(data) > max_rows:
            data = data.iloc[-max_rows:]
        if len(data) < MIN_ROWS:
            raise DataNotAvailableError(
                f"Only {len(data)} bars for {model.symbol} {model.timeframe}; "
                f"need at least {MIN_ROWS}."
            )
        return data

    @staticmethod
    def _chronological_split(n: int, embargo: int = 0) -> tuple[slice, slice, slice]:
        """Chronological split with gaps around label boundaries.

        A label at t observes up to ``horizon`` future bars.  Removing that
        many observations at each boundary prevents train/validation/test rows
        from sharing future price information.
        """
        train_end = int(n * 0.7)
        valid_end = int(n * 0.85)
        if embargo < 0 or train_end <= embargo or valid_end - train_end <= 2 * embargo:
            raise MlTrainingError("Not enough rows for the requested embargo.")
        return (
            slice(0, train_end - embargo),
            slice(train_end + embargo, valid_end - embargo),
            slice(valid_end + embargo, n),
        )

    def _train_supervised(self, model: MlModel) -> tuple[dict[str, Any], Path]:
        from quantlab.infrastructure.ml.trainers import TRAINERS

        if model.algorithm not in TRAINERS:
            raise MlTrainingError(f"Unknown algorithm: {model.algorithm}")
        data = self._prepare(model)
        config = model.config
        horizon = int(config.get("horizon", 12))
        direction = str(config.get("direction", "long"))
        if direction not in ("long", "short"):
            raise MlTrainingError("config.direction must be 'long' or 'short'.")
        labels = triple_barrier_labels(
            data,
            horizon=horizon,
            sl_atr=float(config.get("sl_atr", 2.0)),
            tp_atr=float(config.get("tp_atr", 3.0)),
        )
        features = build_features(data)
        y_all = target_vector(labels, model.target, direction=direction)
        mask = labels["valid"] & ~features.isna().any(axis=1) & ~y_all.isna()
        x = features.loc[mask, feature_names()].to_numpy(dtype=np.float64)
        y = y_all[mask].to_numpy(dtype=np.float64)
        if len(x) < MIN_ROWS:
            raise MlTrainingError(f"Only {len(x)} labeled rows after cleaning.")

        embargo = int(config.get("embargo_bars", horizon))
        train, valid, test = self._chronological_split(len(x), embargo=embargo)
        if test.stop - test.start < 20:
            raise MlTrainingError("Too few untouched test rows after applying the embargo.")
        task: Literal["classification", "regression"] = (
            "classification" if model.target in CLASSIFICATION_TARGETS else "regression"
        )
        trained = TRAINERS[model.algorithm](
            x[train], y[train], x[valid], y[valid], task, config, feature_names()
        )
        predictions = trained.predict(x[test])
        metrics = self._evaluate(task, y[test], predictions)
        metrics.update(
            {
                "task": task,
                "horizon": horizon,
                "direction": direction,
                "embargo_bars": embargo,
                "rows_train": int(train.stop),
                "rows_valid": int(valid.stop - valid.start),
                "rows_test": int(test.stop - test.start),
                "feature_importances": trained.importances,
            }
        )
        artifact = self._artifact_path(model, "joblib" if model.algorithm != "torch_mlp" else "pt")
        trained.save(artifact)
        # Inference must know which side the model was trained to score; an
        # artifact without this information could accidentally gate shorts with
        # a long-outcome probability.
        artifact.with_suffix(artifact.suffix + ".meta.json").write_text(
            json.dumps({"direction": direction, "target": model.target}), encoding="utf-8"
        )
        return metrics, artifact

    @staticmethod
    def _evaluate(task: str, y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
        from sklearn import metrics as sk

        if task == "classification":
            base_rate = float(np.mean(y_true))
            auc = (
                float(sk.roc_auc_score(y_true, y_pred))
                if 0.0 < base_rate < 1.0
                else 0.5  # degenerate test split
            )
            return {
                "auc": auc,
                "accuracy": float(sk.accuracy_score(y_true, y_pred >= 0.5)),
                "base_rate": base_rate,
                "brier": float(sk.brier_score_loss(y_true, y_pred)),
                "log_loss": float(sk.log_loss(y_true, y_pred, labels=[0.0, 1.0])),
            }
        return {
            "mae": float(sk.mean_absolute_error(y_true, y_pred)),
            "rmse": float(np.sqrt(sk.mean_squared_error(y_true, y_pred))),
            "r2": float(sk.r2_score(y_true, y_pred)),
        }

    # -- reinforcement learning ------------------------------------------------------

    def _train_rl(self, model: MlModel) -> tuple[dict[str, Any], Path]:
        from quantlab.infrastructure.rl.sb3_trainer import train_ppo

        if model.algorithm != "ppo":
            raise MlTrainingError(f"Unknown RL algorithm: {model.algorithm}")
        data = self._prepare(model)
        features = build_features(data)
        mask = ~features.isna().any(axis=1)
        features = features.loc[mask, feature_names()]
        close = data.loc[mask, "close"]

        split = int(len(features) * 0.8)
        artifact = self._artifact_path(model, "zip")
        metrics = train_ppo(
            features.iloc[:split],
            close.iloc[:split],
            features.iloc[split:],
            close.iloc[split:],
            model.config,
            artifact,
        )
        return metrics, artifact

    def _artifact_path(self, model: MlModel, extension: str) -> Path:
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
        return self._artifacts_dir / f"{model.id}.{extension}"

    async def _save(self, model: MlModel) -> MlModel:
        async with self._repositories() as repo:
            return await repo.update(model)
