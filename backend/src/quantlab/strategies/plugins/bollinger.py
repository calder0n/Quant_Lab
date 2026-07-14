"""Bollinger band mean reversion."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class BollingerReversion(Strategy):
    """Buy re-entries from the lower band, sell re-entries from the upper band."""

    strategy_id = "bollinger"
    name = "Bollinger"
    category = "mean_reversion"
    description = "Band re-entry reversion with midline exits."
    PARAMS = (
        ParameterSpec("bb_period", "int", 20, 5, 100),
        ParameterSpec("bb_std", "float", 2.0, 0.5, 4.0),
    )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        lower, mid, upper = ta.bollinger(
            data["close"], int(self.params["bb_period"]), float(self.params["bb_std"])
        )
        return self._frame(
            data,
            long_entry=ta.cross_above(data["close"], lower),
            long_exit=ta.cross_above(data["close"], mid),
            short_entry=ta.cross_below(data["close"], upper),
            short_exit=ta.cross_below(data["close"], mid),
        )
