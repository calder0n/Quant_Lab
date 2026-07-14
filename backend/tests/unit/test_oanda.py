"""Tests for the OANDA client and market data adapter (no network: mock transport)."""

from datetime import datetime
from typing import Any

import httpx
import pytest

from quantlab.domain.market import CANDLE_COLUMNS, Symbol, Timeframe
from quantlab.infrastructure.brokers.oanda.client import OandaApiError, OandaClient
from quantlab.infrastructure.brokers.oanda.market_data import (
    GRANULARITIES,
    INSTRUMENTS,
    OandaMarketDataProvider,
)
from tests.factories import utc


def oanda_candle(time: datetime, price: float, complete: bool = True) -> dict[str, Any]:
    return {
        "time": time.strftime("%Y-%m-%dT%H:%M:%S.000000000Z"),
        "volume": 42,
        "complete": complete,
        "mid": {
            "o": str(price),
            "h": str(price + 0.002),
            "l": str(price - 0.002),
            "c": str(price + 0.001),
        },
        "bid": {"c": str(price)},
        "ask": {"c": str(price + 0.0002)},
    }


class FakeOandaApi:
    """Serves a fixed hourly series, paginated in small pages."""

    def __init__(self, series_start: datetime, total: int, page_size: int = 5) -> None:
        self.times = [series_start + i * Timeframe.H1.delta for i in range(total)]
        self.page_size = page_size
        self.requests: list[dict[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.requests.append(params)
        from_time = datetime.fromisoformat(params["from"].replace("Z", "+00:00"))
        matching = [t for t in self.times if t >= from_time][: self.page_size]
        candles = [oanda_candle(t, 1.1) for t in matching]
        return httpx.Response(200, json={"candles": candles})


def make_provider(api: FakeOandaApi) -> OandaMarketDataProvider:
    transport = httpx.MockTransport(api.handler)
    http = httpx.AsyncClient(base_url="https://api-fxpractice.oanda.com", transport=transport)
    return OandaMarketDataProvider(OandaClient("token", "practice", http=http))


def test_every_symbol_and_timeframe_is_mapped() -> None:
    assert set(INSTRUMENTS) == set(Symbol)
    assert set(GRANULARITIES) == set(Timeframe)
    assert GRANULARITIES[Timeframe.D1] == "D"


async def test_fetch_candles_paginates_until_end() -> None:
    api = FakeOandaApi(series_start=utc(2024, 1, 1), total=12, page_size=5)
    provider = make_provider(api)
    frame = await provider.fetch_candles(
        Symbol.EURUSD, Timeframe.H1, utc(2024, 1, 1), utc(2024, 1, 1, 11)
    )
    assert len(frame) == 12
    assert list(frame.columns) == CANDLE_COLUMNS
    assert frame.index[0] == utc(2024, 1, 1)
    assert frame.index[-1] == utc(2024, 1, 1, 11)
    assert len(api.requests) >= 3  # 12 candles in pages of 5
    assert api.requests[0]["price"] == "MBA"


async def test_fetch_candles_excludes_beyond_end_and_incomplete() -> None:
    api = FakeOandaApi(series_start=utc(2024, 1, 1), total=10, page_size=10)
    provider = make_provider(api)
    frame = await provider.fetch_candles(
        Symbol.EURUSD, Timeframe.H1, utc(2024, 1, 1), utc(2024, 1, 1, 4)
    )
    assert len(frame) == 5  # hours 0..4 only


async def test_fetch_candles_returns_empty_frame_when_no_data() -> None:
    api = FakeOandaApi(series_start=utc(2024, 1, 1), total=0)
    provider = make_provider(api)
    frame = await provider.fetch_candles(
        Symbol.EURUSD, Timeframe.H1, utc(2024, 1, 1), utc(2024, 1, 2)
    )
    assert frame.empty
    assert list(frame.columns) == CANDLE_COLUMNS


async def test_incomplete_candles_are_filtered() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        candles = [
            oanda_candle(utc(2024, 1, 1), 1.1),
            oanda_candle(utc(2024, 1, 1, 1), 1.1, complete=False),
        ]
        return httpx.Response(200, json={"candles": candles})

    http = httpx.AsyncClient(base_url="https://x", transport=httpx.MockTransport(handler))
    provider = OandaMarketDataProvider(OandaClient("token", http=http))
    frame = await provider.fetch_candles(
        Symbol.EURUSD, Timeframe.H1, utc(2024, 1, 1), utc(2024, 1, 1, 1)
    )
    assert len(frame) == 1


async def test_client_raises_on_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    http = httpx.AsyncClient(base_url="https://x", transport=httpx.MockTransport(handler))
    client = OandaClient("bad-token", http=http)
    with pytest.raises(OandaApiError) as excinfo:
        await client.get_candles("EUR_USD", "H1", from_time=utc(2024, 1, 1))
    assert excinfo.value.status_code == 401
    await client.aclose()


async def test_spread_is_ask_minus_bid() -> None:
    api = FakeOandaApi(series_start=utc(2024, 1, 1), total=1)
    provider = make_provider(api)
    frame = await provider.fetch_candles(
        Symbol.EURUSD, Timeframe.H1, utc(2024, 1, 1), utc(2024, 1, 1)
    )
    assert frame["spread"].iloc[0] == pytest.approx(0.0002)
    await provider.aclose()
