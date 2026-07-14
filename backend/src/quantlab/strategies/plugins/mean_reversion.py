"""Z-score mean reversion."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class ZScoreReversion(Strategy):
    """Fade statistically stretched prices back to their rolling mean."""

    strategy_id = "mean_reversion"
    name = "Mean Reversion"
    category = "mean_reversion"
    description = "Z-score entry beyond a threshold, exit near zero."
    PARAMS = (
        ParameterSpec("lookback", "int", 50, 10, 300),
        ParameterSpec("z_entry", "float", 2.0, 0.5, 4.0),
        ParameterSpec("z_exit", "float", 0.25, 0.0, 1.5),
    )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        z = ta.zscore(data["close"], int(self.params["lookback"]))
        z_entry = float(self.params["z_entry"])
        z_exit = float(self.params["z_exit"])
        return self._frame(
            data,
            long_entry=ta.cross_below(z, pd.Series(-z_entry, index=data.index)),
            long_exit=z >= -z_exit,
            short_entry=ta.cross_above(z, pd.Series(z_entry, index=data.index)),
            short_exit=z <= z_exit,
        )
