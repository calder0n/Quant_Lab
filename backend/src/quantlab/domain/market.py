"""Core market concepts: tradable symbols and candle timeframes.

These are broker-agnostic. Broker-specific naming (e.g. OANDA's ``EUR_USD``)
lives inside the corresponding broker adapter, never here.
"""

from datetime import timedelta
from enum import StrEnum


class Symbol(StrEnum):
    """Canonical instrument identifiers used across the whole platform."""

    EURUSD = "EURUSD"
    GBPUSD = "GBPUSD"
    USDJPY = "USDJPY"
    AUDUSD = "AUDUSD"
    XAUUSD = "XAUUSD"
    NAS100 = "NAS100"
    SPX500 = "SPX500"
    US30 = "US30"


# One pip expressed in price units, per instrument (broker convention: 0.0001
# for 4-decimal FX pairs, 0.01 for JPY pairs, 0.1 for gold, 1 point for indices).
PIP_SIZE: dict[Symbol, float] = {
    Symbol.EURUSD: 0.0001,
    Symbol.GBPUSD: 0.0001,
    Symbol.USDJPY: 0.01,
    Symbol.AUDUSD: 0.0001,
    Symbol.XAUUSD: 0.1,
    Symbol.NAS100: 1.0,
    Symbol.SPX500: 1.0,
    Symbol.US30: 1.0,
}


class Timeframe(StrEnum):
    """Candle timeframes supported by the platform."""

    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

    @property
    def seconds(self) -> int:
        return _TIMEFRAME_SECONDS[self]

    @property
    def delta(self) -> timedelta:
        """Duration of one candle."""
        return timedelta(seconds=self.seconds)


_TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
}

CANDLE_COLUMNS = ["open", "high", "low", "close", "volume", "spread"]
