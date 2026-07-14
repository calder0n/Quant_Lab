"""Fair value gap fill."""

import pandas as pd

from quantlab.strategies.base import ParameterSpec, Strategy


class FairValueGap(Strategy):
    """Trade retracements into three-candle imbalances.

    A bullish FVG exists when the current low is above the high of two bars ago
    (an unfilled gap). The gap's upper bound remains an active level for
    ``validity_bars`` bars; when price trades back into it and closes above,
    enter long. Symmetric for bearish gaps.
    """

    strategy_id = "fair_value_gap"
    name = "Fair Value Gap"
    category = "smc"
    description = "Entry on retracement into a three-candle imbalance."
    PARAMS = (
        ParameterSpec("min_gap_atr", "float", 0.3, 0.05, 2.0),
        ParameterSpec("validity_bars", "int", 30, 5, 200),
    )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        average_range = self.atr(data).shift(1)
        min_gap = float(self.params["min_gap_atr"]) * average_range
        validity = int(self.params["validity_bars"])

        bullish_gap = (data["low"] - data["high"].shift(2)) > min_gap
        bearish_gap = (data["low"].shift(2) - data["high"]) > min_gap

        # Level to retest: top of a bullish gap, bottom of a bearish gap.
        bullish_level = data["low"].where(bullish_gap).ffill(limit=validity)
        bearish_level = data["high"].where(bearish_gap).ffill(limit=validity)

        filled_bullish = (data["low"] <= bullish_level) & (data["close"] > bullish_level)
        filled_bearish = (data["high"] >= bearish_level) & (data["close"] < bearish_level)
        return self._frame(
            data,
            long_entry=filled_bullish,
            long_exit=bearish_gap,
            short_entry=filled_bearish,
            short_exit=bullish_gap,
        )
