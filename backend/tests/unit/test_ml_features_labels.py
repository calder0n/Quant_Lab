"""Tests for the feature pipeline and triple-barrier labeling."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from quantlab.ml.features import WARMUP_BARS, build_features, feature_names
from quantlab.ml.labels import ALL_TARGETS, target_vector, triple_barrier_labels
from tests.factories import make_market_data


def test_features_have_stable_names_and_no_nan_after_warmup() -> None:
    data = make_market_data(400)
    features = build_features(data)
    assert list(features.columns) == feature_names()
    assert not features.iloc[WARMUP_BARS:].isna().any().any()
    assert features.index.equals(data.index)


def test_features_are_causal() -> None:
    """Truncating the future must not change past feature values."""
    data = make_market_data(300)
    full = build_features(data)
    truncated = build_features(data.iloc[:-50])
    pd.testing.assert_frame_equal(full.loc[truncated.index], truncated)


def test_hour_encoding_is_cyclical() -> None:
    data = make_market_data(48)
    features = build_features(data)
    norm = features["hour_sin"] ** 2 + features["hour_cos"] ** 2
    np.testing.assert_allclose(norm, 1.0, atol=1e-9)


def crafted_data(closes: list[float], spread: float = 0.0) -> pd.DataFrame:
    """Flat OHLC bars where high=low=close so barrier hits are deterministic."""
    times = pd.DatetimeIndex(
        [datetime(2024, 1, 1, tzinfo=UTC) + pd.Timedelta(hours=i) for i in range(len(closes))],
        tz=UTC,
        name="time",
    )
    values = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "open": values,
            "high": values,
            "low": values,
            "close": values,
            "volume": np.ones(len(values)),
            "spread": np.full(len(values), spread),
        },
        index=times,
    )


def test_triple_barrier_tp_first() -> None:
    # ATR ~ 1 after warmup with these jumps; craft a clear +3 move.
    closes = [100.0] * 30 + [100.0, 104.0, 100.0] + [100.0] * 10
    data = crafted_data(closes)
    labels = triple_barrier_labels(data, horizon=3, sl_atr=2.0, tp_atr=1.0)
    idx = 30  # the bar right before the spike
    assert labels["first_touch"].iloc[idx] == 1
    assert bool(labels["tp_touched"].iloc[idx])


def test_triple_barrier_sl_first_and_tie_is_conservative() -> None:
    closes = [100.0] * 30 + [100.0, 92.0] + [100.0] * 10
    data = crafted_data(closes)
    labels = triple_barrier_labels(data, horizon=3, sl_atr=1.0, tp_atr=1.0)
    assert labels["first_touch"].iloc[30] == -1


def test_triple_barrier_no_touch_and_validity() -> None:
    # Small oscillation (ATR ~ 0.2) with barriers at 2*ATR: never touched.
    closes = [100.0 + 0.2 * (i % 2) for i in range(60)]
    data = crafted_data(closes)
    horizon = 5
    labels = triple_barrier_labels(data, horizon=horizon, sl_atr=2.0, tp_atr=2.0)
    assert (labels["first_touch"].iloc[20:-horizon] == 0).all()
    assert not labels["valid"].iloc[-horizon:].any()
    assert labels["valid"].iloc[20:-horizon].all()


def test_zero_volatility_rows_are_invalid() -> None:
    labels = triple_barrier_labels(crafted_data([100.0] * 60), horizon=5, sl_atr=2.0, tp_atr=2.0)
    assert not labels["valid"].any()  # flat series: ATR is zero everywhere


def test_forward_return_matches_horizon() -> None:
    data = make_market_data(200)
    horizon = 10
    labels = triple_barrier_labels(data, horizon=horizon, sl_atr=2.0, tp_atr=3.0)
    expected = data["close"].iloc[50 + horizon] / data["close"].iloc[50] - 1.0
    assert labels["forward_return"].iloc[50] == pytest.approx(expected)


def test_target_vectors() -> None:
    data = make_market_data(300)
    labels = triple_barrier_labels(data, horizon=6, sl_atr=1.0, tp_atr=1.0)
    for target in ALL_TARGETS:
        y = target_vector(labels, target)
        assert len(y) == len(data)
    win = target_vector(labels, "win")
    sl = target_vector(labels, "sl_hit")
    assert ((win + sl) <= 1.0 + 1e-9).all()  # mutually exclusive first touches
    with pytest.raises(ValueError, match="Unknown target"):
        target_vector(labels, "nope")


def test_horizon_must_be_positive() -> None:
    with pytest.raises(ValueError, match="horizon"):
        triple_barrier_labels(make_market_data(50), horizon=0, sl_atr=1.0, tp_atr=1.0)
