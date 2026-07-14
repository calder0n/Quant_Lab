"""RSI mean reversion."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class RsiReversion(Strategy):
    """Buy oversold, sell overbought; exit when RSI normalizes."""

    strategy_id = "rsi"
    name = "RSI"
    category = "mean_reversion"
    description = "RSI oversold/overbought reversion with midline exits."
    PARAMS = (
        ParameterSpec("rsi_period", "int", 14, 2, 50),
        ParameterSpec("oversold", "float", 30.0, 5.0, 45.0),
        ParameterSpec("overbought", "float", 70.0, 55.0, 95.0),
    )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        rsi = ta.rsi(data["close"], int(self.params["rsi_period"]))
        oversold = float(self.params["oversold"])
        overbought = float(self.params["overbought"])
        return self._frame(
            data,
            long_entry=ta.cross_above(rsi, pd.Series(oversold, index=data.index)),
            long_exit=rsi >= 50.0,
            short_entry=ta.cross_below(rsi, pd.Series(overbought, index=data.index)),
            short_exit=rsi <= 50.0,
        )
