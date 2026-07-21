"""Session-VWAP deviation reversion."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class VwapReversion(Strategy):
    """Fade stretched deviations from the daily-anchored VWAP back to it."""

    strategy_id = "vwap"
    name = "VWAP"
    category = "mean_reversion"
    description = "Buy below / sell above the session VWAP by a deviation threshold."
    PARAMS = (
        ParameterSpec("deviation_pct", "float", 0.004, 0.0005, 0.05),
        ParameterSpec("exit_at_vwap", "bool", True),
    )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        vwap = ta.session_vwap(data)
        deviation = float(self.params["deviation_pct"])
        below = data["close"] < vwap * (1.0 - deviation)
        above = data["close"] > vwap * (1.0 + deviation)
        long_entry = below & ~below.shift(1, fill_value=False)
        short_entry = above & ~above.shift(1, fill_value=False)
        if bool(self.params["exit_at_vwap"]):
            long_exit = ta.cross_above(data["close"], vwap)
            short_exit = ta.cross_below(data["close"], vwap)
        else:
            long_exit = short_entry
            short_exit = long_entry
        return self._frame(
            data,
            long_entry=long_entry,
            long_exit=long_exit,
            short_entry=short_entry,
            short_exit=short_exit,
        )

    def plot_overlays(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        return {"VWAP": ta.session_vwap(data)}
