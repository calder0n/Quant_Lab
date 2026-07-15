"""Smart Money Concepts: break of structure on confirmed swings."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class SmartMoneyConcepts(Strategy):
    """Vectorized market-structure approximation.

    Swing highs/lows are confirmed ``swing_strength`` bars after the fact
    (no lookahead). A close breaking the last confirmed swing high is a bullish
    break of structure (BOS) and enters long; breaking the last swing low
    enters short. Opposite BOS closes the position.
    """

    strategy_id = "smc"
    name = "Smart Money Concepts"
    category = "smc"
    description = "Break of structure over confirmed swing highs/lows."
    PARAMS = (ParameterSpec("swing_strength", "int", 5, 2, 30),)

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        strength = int(self.params["swing_strength"])
        swing_high = ta.confirmed_swing_high(data, strength)
        swing_low = ta.confirmed_swing_low(data, strength)
        bos_up = ta.cross_above(data["close"], swing_high)
        bos_down = ta.cross_below(data["close"], swing_low)
        return self._frame(
            data,
            long_entry=bos_up,
            long_exit=bos_down,
            short_entry=bos_down,
            short_exit=bos_up,
        )

    def plot_overlays(self, data: pd.DataFrame) -> dict[str, pd.Series]:
        strength = int(self.params["swing_strength"])
        return {
            "Swing high": ta.confirmed_swing_high(data, strength),
            "Swing low": ta.confirmed_swing_low(data, strength),
        }
