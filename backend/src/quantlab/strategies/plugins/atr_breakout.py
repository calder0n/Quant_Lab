"""ATR-scaled volatility breakout."""

import pandas as pd

from quantlab.strategies.base import ParameterSpec, Strategy


class AtrBreakout(Strategy):
    """Enter when the close moves more than k*ATR beyond the previous close."""

    strategy_id = "atr_breakout"
    name = "ATR Breakout"
    category = "breakout"
    description = "Momentum entry on candles larger than a multiple of ATR."
    PARAMS = (ParameterSpec("breakout_atr", "float", 1.5, 0.5, 5.0),)

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        threshold = float(self.params["breakout_atr"]) * self.atr(data).shift(1)
        change = data["close"] - data["close"].shift(1)
        return self._frame(
            data,
            long_entry=change > threshold,
            short_entry=change < -threshold,
            long_exit=change < -threshold,
            short_exit=change > threshold,
        )
