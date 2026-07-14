"""ICT killzone displacement."""

import pandas as pd

from quantlab.strategies import indicators as ta
from quantlab.strategies.base import ParameterSpec, Strategy


class IctKillzone(Strategy):
    """Displacement candles inside an ICT killzone.

    Enters in the direction of a displacement candle (body larger than
    ``displacement_atr`` ATRs) that prints inside the configured killzone hours
    (default: London open, UTC). Exits on an opposite displacement.
    """

    strategy_id = "ict"
    name = "ICT"
    category = "smc"
    description = "Killzone-filtered displacement momentum."
    PARAMS = (
        ParameterSpec("killzone_start", "int", 7, 0, 23),
        ParameterSpec("killzone_end", "int", 10, 0, 23),
        ParameterSpec("displacement_atr", "float", 1.5, 0.5, 4.0),
    )

    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        assert isinstance(data.index, pd.DatetimeIndex)
        body = ta.candle_body(data)
        displaced = body > float(self.params["displacement_atr"]) * self.atr(data).shift(1)
        bullish = displaced & (data["close"] > data["open"])
        bearish = displaced & (data["close"] < data["open"])
        start = int(self.params["killzone_start"])
        end = int(self.params["killzone_end"])
        hours = pd.Series(data.index.hour, index=data.index)
        in_killzone = (hours >= start) & (hours <= end) if start <= end else (
            (hours >= start) | (hours <= end)
        )
        return self._frame(
            data,
            long_entry=bullish & in_killzone,
            long_exit=bearish,
            short_entry=bearish & in_killzone,
            short_exit=bullish,
        )
