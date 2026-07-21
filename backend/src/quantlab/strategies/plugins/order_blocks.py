"""Order block retest."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class OrderBlocks(Strategy):
    """Vectorized order-block approximation.

    A bullish order block is the last bearish candle immediately before a
    bullish displacement (body > ``displacement_atr`` * ATR). Its high stays
    an active demand level for ``validity_bars`` bars; a pullback that touches
    the level and closes back above it enters long. Symmetric for shorts.
    """

    strategy_id = "order_blocks"
    name = "Order Blocks"
    category = "smc"
    description = "Retest of the candle that originated a displacement move."
    PARAMS = (
        ParameterSpec("displacement_atr", "float", 1.5, 0.5, 4.0),
        ParameterSpec("validity_bars", "int", 30, 5, 200),
    )

    def _zones(self, data: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        body = ta.candle_body(data)
        displaced = body > float(self.params["displacement_atr"]) * self.atr(data).shift(1)
        bullish_move = displaced & (data["close"] > data["open"])
        bearish_move = displaced & (data["close"] < data["open"])
        previous_bearish = (data["close"] < data["open"]).shift(1, fill_value=False)
        previous_bullish = (data["close"] > data["open"]).shift(1, fill_value=False)
        validity = int(self.params["validity_bars"])

        # Demand zone top: high of the bearish candle preceding a bullish displacement.
        demand = data["high"].shift(1).where(bullish_move & previous_bearish).ffill(limit=validity)
        supply = data["low"].shift(1).where(bearish_move & previous_bullish).ffill(limit=validity)
        return demand, supply, bullish_move, bearish_move

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        demand, supply, bullish_move, bearish_move = self._zones(data)
        touched_demand = (data["low"] <= demand) & (data["close"] > demand)
        touched_supply = (data["high"] >= supply) & (data["close"] < supply)
        return self._frame(
            data,
            long_entry=touched_demand,
            long_exit=bearish_move,
            short_entry=touched_supply,
            short_exit=bullish_move,
        )

    def plot_overlays(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        demand, supply, _, _ = self._zones(data)
        return {"Demand": demand, "Supply": supply}
