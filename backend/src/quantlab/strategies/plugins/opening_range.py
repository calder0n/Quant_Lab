"""Opening range breakout."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class OpeningRange(Strategy):
    """Break of the range formed by the first N bars of each UTC day.

    The range only becomes tradable after those N bars have closed, so there is
    no lookahead: before that, entries are suppressed.
    """

    strategy_id = "opening_range"
    name = "Opening Range"
    category = "breakout"
    description = "Breakout of the first N bars of the day, long and short."
    PARAMS = (ParameterSpec("range_bars", "int", 3, 1, 12),)

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        assert isinstance(data.index, pd.DatetimeIndex)
        bar_number = ta.bar_number_in_day(data.index)
        range_bars = int(self.params["range_bars"])
        in_range = bar_number < range_bars
        day = data.index.date
        range_high = data["high"].where(in_range).groupby(day).cummax().groupby(day).ffill()
        range_low = data["low"].where(in_range).groupby(day).cummin().groupby(day).ffill()
        tradable = bar_number >= range_bars
        long_entry = tradable & ta.cross_above(data["close"], range_high)
        short_entry = tradable & ta.cross_below(data["close"], range_low)
        return self._frame(
            data,
            long_entry=long_entry,
            short_entry=short_entry,
            long_exit=short_entry,
            short_exit=long_entry,
        )
