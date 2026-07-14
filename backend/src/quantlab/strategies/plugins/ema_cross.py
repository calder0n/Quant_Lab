"""EMA crossover trend following."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class EmaCross(Strategy):
    """Long when the fast EMA crosses above the slow EMA; short on the inverse."""

    strategy_id = "ema_cross"
    name = "EMA Cross"
    category = "trend"
    description = "Fast/slow EMA crossover, long and short."
    PARAMS = (
        ParameterSpec("fast_period", "int", 12, 3, 100),
        ParameterSpec("slow_period", "int", 48, 10, 400),
    )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        fast_period = int(self.params["fast_period"])
        slow_period = int(self.params["slow_period"])
        if fast_period >= slow_period:  # keep the search space smooth for optimizers
            fast_period, slow_period = min(fast_period, slow_period - 1), slow_period
        fast = ta.ema(data["close"], fast_period)
        slow = ta.ema(data["close"], slow_period)
        up = ta.cross_above(fast, slow)
        down = ta.cross_below(fast, slow)
        return self._frame(data, long_entry=up, long_exit=down, short_entry=down, short_exit=up)
