"""Load a trained classification model for meta-labeling inference.

Turns a persisted model artifact into a predictor callable that scores each
candle with the model's probability of a trade opened there being a winner.
Used by the shared ML entry filter (``use_ml_filter``) to gate strategy entries
on model confidence, the same way the other entry filters gate on price rules.
"""

import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from quantlab.ml.features import build_features, feature_names

WinPredictor = Callable[[pd.DataFrame], pd.DataFrame]


class ModelNotUsableError(ValueError):
    """Raised when a model cannot be used as a meta-labeling filter."""


def load_win_predictor(artifacts_dir: Path, model_id: str) -> WinPredictor:
    """Return a callable mapping candles -> per-bar P(win) for ``model_id``.

    Only classification models (which expose ``predict_proba``) qualify; the
    artifact filename is deterministic (``<id>.joblib``), so no database lookup
    is needed. Raises :class:`ModelNotUsableError` if the model is missing or is
    not a classifier (e.g. a regression or RL model).
    """
    import joblib

    path = artifacts_dir / f"{model_id}.joblib"
    if not path.exists():
        raise ModelNotUsableError(
            f"No trained classification model {model_id}. Train a 'win' model first."
        )
    model = joblib.load(path)
    if not hasattr(model, "predict_proba"):
        raise ModelNotUsableError(
            "Model is not a classifier; the ML filter needs a classification target (e.g. win)."
        )

    names = feature_names()
    meta_path = path.with_suffix(path.suffix + ".meta.json")
    direction = "long"  # legacy artifacts were trained with the old long label.
    if meta_path.exists():
        direction = str(
            json.loads(meta_path.read_text(encoding="utf-8")).get("direction", direction)
        )
    if direction not in ("long", "short"):
        raise ModelNotUsableError("Model metadata has an invalid trade direction.")

    def predict(data: pd.DataFrame) -> pd.DataFrame:
        features = build_features(data)
        usable = ~features[names].isna().any(axis=1)
        proba = pd.DataFrame(np.nan, index=data.index, columns=["long", "short"])
        if usable.any():
            x = features.loc[usable, names].to_numpy(dtype=np.float64)
            proba.loc[usable, direction] = model.predict_proba(x)[:, 1]
        return proba

    return predict
