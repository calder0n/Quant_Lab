"""MACD signal-line crossover."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class MacdCross(Strategy):
    """Long when MACD crosses above its signal line below zero-adjustable filter."""

    strategy_id = "macd"
    name = "MACD"
    category = "trend"
    description = "MACD/signal crossover with optional zero-line filter."
    PARAMS = (
        ParameterSpec("fast_period", "int", 12, 3, 50),
        ParameterSpec("slow_period", "int", 26, 10, 200),
        ParameterSpec("signal_period", "int", 9, 3, 50),
        ParameterSpec("zero_line_filter", "bool", False),
    )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        fast_period = int(self.params["fast_period"])
        slow_period = int(self.params["slow_period"])
        if fast_period >= slow_period:
            fast_period = slow_period - 1
        macd_line, signal_line, _ = ta.macd(
            data["close"], fast_period, slow_period, int(self.params["signal_period"])
        )
        up = ta.cross_above(macd_line, signal_line)
        down = ta.cross_below(macd_line, signal_line)
        if bool(self.params["zero_line_filter"]):
            up &= macd_line < 0  # buy dips: cross while still below zero
            down &= macd_line > 0
        return self._frame(
            data,
            long_entry=up,
            long_exit=ta.cross_below(macd_line, signal_line),
            short_entry=down,
            short_exit=ta.cross_above(macd_line, signal_line),
        )
