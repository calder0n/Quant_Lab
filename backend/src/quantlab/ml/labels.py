"""Triple-barrier labeling.

For every bar we simulate hypothetical long *and* short entries at the close,
with ATR-scaled barriers watched for ``horizon`` bars.  Keeping both directions
prevents a long-outcome model from being applied to short signals.

- ``first_touch``: +1 take-profit first, -1 stop-loss first, 0 neither.
  If both are touched within the same bar the stop wins (conservative).
- ``tp_touched``: the target was reached at any point within the horizon.
- ``forward_return``: raw close-to-close return over the horizon (regression).

The last ``horizon`` rows cannot be labeled and must be dropped by the caller
(``valid`` column is False there).
"""

import numpy as np
import pandas as pd

from quantlab.strategies import indicators as ta


def triple_barrier_labels(
    data: pd.DataFrame, horizon: int, sl_atr: float, tp_atr: float
) -> pd.DataFrame:
    if horizon < 1:
        raise ValueError("horizon must be >= 1")
    close = data["close"].to_numpy(dtype=float)
    high = data["high"].to_numpy(dtype=float)
    low = data["low"].to_numpy(dtype=float)
    atr = ta.atr(data, 14).to_numpy(dtype=float)
    n = len(data)

    long_tp_level = close + tp_atr * atr
    long_sl_level = close - sl_atr * atr
    short_tp_level = close - tp_atr * atr
    short_sl_level = close + sl_atr * atr

    infinity = np.iinfo(np.int64).max
    tp_time = np.full(n, infinity, dtype=np.int64)
    sl_time = np.full(n, infinity, dtype=np.int64)

    for offset in range(1, horizon + 1):
        future_high = np.full(n, -np.inf)
        future_low = np.full(n, np.inf)
        future_high[: n - offset] = high[offset:]
        future_low[: n - offset] = low[offset:]
        tp_hit_now = (future_high >= long_tp_level) & (tp_time == infinity)
        sl_hit_now = (future_low <= long_sl_level) & (sl_time == infinity)
        tp_time[tp_hit_now] = offset
        sl_time[sl_hit_now] = offset

    first_touch = np.zeros(n, dtype=np.int64)
    first_touch[tp_time < sl_time] = 1
    first_touch[sl_time <= tp_time] = -1
    first_touch[(tp_time == infinity) & (sl_time == infinity)] = 0

    short_tp_time = np.full(n, infinity, dtype=np.int64)
    short_sl_time = np.full(n, infinity, dtype=np.int64)
    for offset in range(1, horizon + 1):
        future_high = np.full(n, -np.inf)
        future_low = np.full(n, np.inf)
        future_high[: n - offset] = high[offset:]
        future_low[: n - offset] = low[offset:]
        tp_hit_now = (future_low <= short_tp_level) & (short_tp_time == infinity)
        sl_hit_now = (future_high >= short_sl_level) & (short_sl_time == infinity)
        short_tp_time[tp_hit_now] = offset
        short_sl_time[sl_hit_now] = offset
    short_first_touch = np.zeros(n, dtype=np.int64)
    short_first_touch[short_tp_time < short_sl_time] = 1
    short_first_touch[short_sl_time <= short_tp_time] = -1
    short_first_touch[(short_tp_time == infinity) & (short_sl_time == infinity)] = 0

    forward_return = np.full(n, np.nan)
    forward_return[: n - horizon] = close[horizon:] / close[: n - horizon] - 1.0

    valid = np.ones(n, dtype=bool)
    valid[n - horizon :] = False
    valid &= ~np.isnan(atr)
    valid &= atr > 0  # zero volatility makes the barriers degenerate

    return pd.DataFrame(
        {
            "first_touch": first_touch,
            "tp_touched": tp_time < infinity,
            "short_first_touch": short_first_touch,
            "short_tp_touched": short_tp_time < infinity,
            "forward_return": forward_return,
            "valid": valid,
        },
        index=data.index,
    )


def target_vector(labels: pd.DataFrame, target: str, direction: str = "long") -> pd.Series:
    """Extract one model target from the label frame."""
    if direction not in ("long", "short"):
        raise ValueError("direction must be 'long' or 'short'")
    touch = "first_touch" if direction == "long" else "short_first_touch"
    tp_touch = "tp_touched" if direction == "long" else "short_tp_touched"
    if target == "win":
        return (labels[touch] == 1).astype(float)
    if target == "sl_hit":
        return (labels[touch] == -1).astype(float)
    if target == "tp_hit":
        return labels[tp_touch].astype(float)
    if target == "expected_move":
        returns = labels["forward_return"].astype(float)
        return returns if direction == "long" else -returns
    raise ValueError(f"Unknown target: {target}")


CLASSIFICATION_TARGETS = {"win", "sl_hit", "tp_hit"}
REGRESSION_TARGETS = {"expected_move"}
ALL_TARGETS = CLASSIFICATION_TARGETS | REGRESSION_TARGETS
