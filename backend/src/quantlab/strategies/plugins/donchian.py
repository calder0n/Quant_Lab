"""Donchian channel breakout."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class DonchianBreakout(Strategy):
    """Break of the N-bar highest high / lowest low, exit at the channel mid."""

    strategy_id = "donchian"
    name = "Donchian"
    category = "breakout"
    description = "Classic turtle-style channel breakout."
    PARAMS = (ParameterSpec("channel_period", "int", 20, 5, 200),)

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        upper, lower = ta.donchian(data, int(self.params["channel_period"]))
        mid = (upper + lower) / 2.0
        return self._frame(
            data,
            long_entry=data["close"] > upper,
            long_exit=ta.cross_below(data["close"], mid),
            short_entry=data["close"] < lower,
            short_exit=ta.cross_above(data["close"], mid),
        )

    def plot_overlays(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        upper, lower = ta.donchian(data, int(self.params["channel_period"]))
        return {"Donchian high": upper, "Donchian low": lower, "Mid": (upper + lower) / 2.0}
