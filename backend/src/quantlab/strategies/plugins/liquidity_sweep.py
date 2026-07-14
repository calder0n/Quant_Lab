"""Liquidity sweep reversal."""

import pandas as pd

from quantlab.strategies.base import ParameterSpec, Strategy


class LiquiditySweep(Strategy):
    """Fade stop hunts beyond recent extremes.

    A bearish sweep: the high pierces the previous N-bar high but the candle
    closes back below it with a meaningful wick — resting buy-side liquidity
    was taken and rejected, so enter short. Symmetric for longs at swept lows.
    """

    strategy_id = "liquidity_sweep"
    name = "Liquidity Sweep"
    category = "smc"
    description = "Reversal after a wick takes out a recent extreme and closes back."
    PARAMS = (
        ParameterSpec("lookback", "int", 50, 10, 300),
        ParameterSpec("min_wick_atr", "float", 0.5, 0.1, 3.0),
    )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        lookback = int(self.params["lookback"])
        prior_high = data["high"].rolling(lookback).max().shift(1)
        prior_low = data["low"].rolling(lookback).min().shift(1)
        min_wick = float(self.params["min_wick_atr"]) * self.atr(data).shift(1)

        upper_wick = data["high"] - data[["open", "close"]].max(axis=1)
        lower_wick = data[["open", "close"]].min(axis=1) - data["low"]

        swept_highs = (data["high"] > prior_high) & (data["close"] < prior_high)
        swept_lows = (data["low"] < prior_low) & (data["close"] > prior_low)
        short_entry = swept_highs & (upper_wick > min_wick)
        long_entry = swept_lows & (lower_wick > min_wick)
        return self._frame(
            data,
            long_entry=long_entry,
            long_exit=short_entry,
            short_entry=short_entry,
            short_exit=long_entry,
        )
