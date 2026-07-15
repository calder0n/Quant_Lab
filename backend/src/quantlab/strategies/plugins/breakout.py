"""Confirmed range breakout with ATR buffer."""

import pandas as pd

from quantlab.strategies.base import ParameterSpec, Strategy


class BufferedBreakout(Strategy):
    """Break of the N-bar close extreme confirmed by an ATR-scaled buffer.

    The buffer filters out marginal breaks that immediately mean-revert.
    """

    strategy_id = "breakout"
    name = "Breakout"
    category = "breakout"
    description = "N-bar extreme break confirmed by an ATR buffer."
    PARAMS = (
        ParameterSpec("lookback", "int", 50, 10, 300),
        ParameterSpec("buffer_atr", "float", 0.25, 0.0, 2.0),
        ParameterSpec("exit_lookback", "int", 20, 5, 150),
    )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        buffer = float(self.params["buffer_atr"]) * self.atr(data)
        highest = data["close"].rolling(int(self.params["lookback"])).max().shift(1)
        lowest = data["close"].rolling(int(self.params["lookback"])).min().shift(1)
        exit_high = data["close"].rolling(int(self.params["exit_lookback"])).max().shift(1)
        exit_low = data["close"].rolling(int(self.params["exit_lookback"])).min().shift(1)
        return self._frame(
            data,
            long_entry=data["close"] > highest + buffer,
            long_exit=data["close"] < exit_low,
            short_entry=data["close"] < lowest - buffer,
            short_exit=data["close"] > exit_high,
        )

    def plot_overlays(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        lookback = int(self.params["lookback"])
        return {
            "Breakout high": data["close"].rolling(lookback).max().shift(1),
            "Breakout low": data["close"].rolling(lookback).min().shift(1),
        }
