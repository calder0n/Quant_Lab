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

    def _levels(self, data: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        min_gap = float(self.params["min_gap_atr"]) * self.atr(data).shift(1)
        validity = int(self.params["validity_bars"])
        bullish_gap = (data["low"] - data["high"].shift(2)) > min_gap
        bearish_gap = (data["low"].shift(2) - data["high"]) > min_gap
        # Level to retest: top of a bullish gap, bottom of a bearish gap.
        bullish_level = data["low"].where(bullish_gap).ffill(limit=validity)
        bearish_level = data["high"].where(bearish_gap).ffill(limit=validity)
        return bullish_level, bearish_level, bullish_gap, bearish_gap

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        bullish_level, bearish_level, bullish_gap, bearish_gap = self._levels(data)
        filled_bullish = (data["low"] <= bullish_level) & (data["close"] > bullish_level)
        filled_bearish = (data["high"] >= bearish_level) & (data["close"] < bearish_level)
        return self._frame(
            data,
            long_entry=filled_bullish,
            long_exit=bearish_gap,
            short_entry=filled_bearish,
            short_exit=bullish_gap,
        )

    def plot_overlays(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        bullish_level, bearish_level, _, _ = self._levels(data)
        return {"FVG support": bullish_level, "FVG resistance": bearish_level}
