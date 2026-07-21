"""OANDA implementation of the ``MarketDataProvider`` port.

Translates canonical QuantLab symbols/timeframes into OANDA instrument and
granularity names, paginates the candles endpoint (max 5000 per request) and
normalizes the payload into the platform's candle DataFrame format.
"""

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from quantlab.application.ports import MarketDataProvider
from quantlab.domain.market import CANDLE_COLUMNS, Symbol, Timeframe
from quantlab.infrastructure.brokers.oanda.client import (
    MAX_CANDLES_PER_REQUEST,
    OandaClient,
)

INSTRUMENTS: dict[Symbol, str] = {
    Symbol.EURUSD: "EUR_USD",
    Symbol.GBPUSD: "GBP_USD",
    Symbol.USDJPY: "USD_JPY",
    Symbol.AUDUSD: "AUD_USD",
    Symbol.XAUUSD: "XAU_USD",
    Symbol.NAS100: "NAS100_USD",
    Symbol.SPX500: "SPX500_USD",
    Symbol.US30: "US30_USD",
}

GRANULARITIES: dict[Timeframe, str] = {
    Timeframe.M1: "M1",
    Timeframe.M5: "M5",
    Timeframe.M15: "M15",
    Timeframe.M30: "M30",
    Timeframe.H1: "H1",
    Timeframe.H4: "H4",
    Timeframe.D1: "D",
}


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _to_row(candle: dict[str, Any]) -> dict[str, float | int]:
    mid = candle["mid"]
    spread = float(candle["ask"]["c"]) - float(candle["bid"]["c"])
    return {
        "open": float(mid["o"]),
        "high": float(mid["h"]),
        "low": float(mid["l"]),
        "close": float(mid["c"]),
        "volume": int(candle["volume"]),
        "spread": round(spread, 6),
    }


class OandaMarketDataProvider(MarketDataProvider):
    """Historical candles from OANDA (mid prices, completed candles only)."""

    def __init__(self, client: OandaClient) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "oanda"

    async def fetch_candles(
        self, symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime
    ) -> pd.DataFrame:
        instrument = INSTRUMENTS[symbol]
        granularity = GRANULARITIES[timeframe]
        times: list[datetime] = []
        rows: list[dict[str, float | int]] = []

        cursor = start
        while cursor <= end:
            batch = await self._client.get_candles(
                instrument, granularity, from_time=cursor, count=MAX_CANDLES_PER_REQUEST
            )
            if not batch:
                break
            for candle in batch:
                candle_time = _parse_time(candle["time"])
                if candle_time > end or not candle["complete"]:
                    continue
                times.append(candle_time)
                rows.append(_to_row(candle))
            last_time = _parse_time(batch[-1]["time"])
            next_cursor = last_time + timeframe.delta
            if last_time >= end or next_cursor <= cursor:
                break
            cursor = next_cursor

        frame = pd.DataFrame(rows, index=pd.DatetimeIndex(times, tz=UTC, name="time"))
        if frame.empty:
            frame = pd.DataFrame(
                columns=CANDLE_COLUMNS, index=pd.DatetimeIndex([], tz=UTC, name="time")
            )
        return frame

    async def aclose(self) -> None:
        await self._client.aclose()
