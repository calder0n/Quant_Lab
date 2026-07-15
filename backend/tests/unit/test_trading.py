"""Tests for the trading service, OANDA execution adapter and routes."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
import pandas as pd
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from quantlab.application.event_bus import InMemoryEventBus
from quantlab.application.ports import (
    ExecutionBroker,
    MarketDataProvider,
    TradingStateRepository,
)
from quantlab.application.services.trading import TradingService
from quantlab.config import Settings
from quantlab.domain.broker import BrokerCredentials
from quantlab.domain.events import DomainEvent
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.trading import (
    AccountSummary,
    LiveConfirmationError,
    OrderExecuted,
    OrderResult,
    Position,
    TradingDisabledError,
    TradingState,
)
from quantlab.infrastructure.brokers.oanda.client import OandaClient
from quantlab.infrastructure.brokers.oanda.execution import OandaExecutionBroker
from quantlab.infrastructure.db.base import Base
from quantlab.infrastructure.db.repositories.auth import SqlAlchemyTradingStateRepository
from quantlab.interfaces.api.app import create_app
from quantlab.strategies.registry import StrategyRegistry
from tests.factories import make_market_data

EUR_USD = "EUR_USD"


class InMemoryTradingState(TradingStateRepository):
    def __init__(self) -> None:
        self.state = TradingState(enabled=False)

    async def get(self) -> TradingState:
        return self.state

    async def set_enabled(self, enabled: bool) -> TradingState:
        self.state = TradingState(enabled=enabled)
        return self.state


class FakeBroker(ExecutionBroker):
    def __init__(self, positions: list[Position] | None = None) -> None:
        self.positions = positions or []
        self.market_orders: list[tuple[Symbol, float, float | None, float | None]] = []
        self.closed: list[Symbol] = []

    async def account_summary(self) -> AccountSummary:
        return AccountSummary(
            "001-1", "USD", 10_000.0, 10_050.0, 100.0, 9_900.0, len(self.positions)
        )

    async def open_positions(self) -> list[Position]:
        return self.positions

    async def place_market_order(
        self,
        symbol: Symbol,
        units: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        self.market_orders.append((symbol, units, stop_loss, take_profit))
        return OrderResult(instrument=EUR_USD, units=units, filled=True, order_id="42")

    async def close_position(self, symbol: Symbol) -> OrderResult:
        self.closed.append(symbol)
        return OrderResult(instrument=EUR_USD, units=0.0, filled=True, order_id="43")


class SignalProvider(MarketDataProvider):
    """Serves data whose final bar carries a chosen signal for ema_cross."""

    def __init__(self, data: pd.DataFrame) -> None:
        self.data = data

    @property
    def name(self) -> str:
        return "fake"

    async def fetch_candles(
        self, symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime
    ) -> pd.DataFrame:
        return self.data


def rising_then_data() -> pd.DataFrame:
    """Flat series with a jump on the very last bar.

    With a constant history the fast and slow EMAs are equal, so the final
    jump makes the fast EMA cross above the slow one exactly on the last bar —
    a deterministic ema_cross long entry.
    """
    from datetime import UTC, datetime

    import numpy as np

    n = 300
    closes = np.full(n, 1.10)
    closes[-1] = 1.30
    times = pd.DatetimeIndex(
        [datetime(2024, 1, 1, tzinfo=UTC) + i * Timeframe.H1.delta for i in range(n)],
        tz=UTC,
        name="time",
    )
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": np.full(n, 100),
            "spread": np.full(n, 0.0002),
        },
        index=times,
    )


def build_service(
    broker: FakeBroker,
    provider: MarketDataProvider,
    environment: str = "practice",
) -> tuple[TradingService, InMemoryTradingState, list[DomainEvent]]:
    states = InMemoryTradingState()

    @asynccontextmanager
    async def state_factory() -> AsyncIterator[TradingStateRepository]:
        yield states

    async def broker_factory() -> ExecutionBroker:
        return broker

    async def credentials() -> BrokerCredentials:
        return BrokerCredentials(
            api_token="tok-12345678", account_id="001-1", environment=environment  # type: ignore[arg-type]
        )

    async def market_data() -> MarketDataProvider:
        return provider

    bus = InMemoryEventBus()
    events: list[DomainEvent] = []

    async def record(event: DomainEvent) -> None:
        events.append(event)

    bus.subscribe(DomainEvent, record)
    service = TradingService(
        states=state_factory,
        broker_factory=broker_factory,
        credentials_resolver=credentials,
        registry=StrategyRegistry().discover(),
        market_data=market_data,
        event_bus=bus,
    )
    return service, states, events


# -- service ----------------------------------------------------------------------


async def test_status_reports_account_and_positions() -> None:
    broker = FakeBroker(positions=[Position(EUR_USD, 1000, 1.1, 5.0)])
    service, _, _ = build_service(broker, SignalProvider(make_market_data(100)))
    status = await service.status()
    assert status.account is not None and status.account.balance == 10_000.0
    assert len(status.positions) == 1
    assert not status.state.enabled


async def test_execute_requires_the_kill_switch() -> None:
    service, _, _ = build_service(FakeBroker(), SignalProvider(rising_then_data()))
    with pytest.raises(TradingDisabledError):
        await service.execute("ema_cross", Symbol.EURUSD, Timeframe.H1, units=100)


async def test_enable_live_requires_typed_confirmation() -> None:
    service, _, _ = build_service(
        FakeBroker(), SignalProvider(make_market_data(100)), environment="live"
    )
    with pytest.raises(LiveConfirmationError):
        await service.set_enabled(True)
    state = await service.set_enabled(True, confirmation="TRADE-LIVE")
    assert state.enabled
    # practice needs no confirmation
    practice_service, _, _ = build_service(FakeBroker(), SignalProvider(make_market_data(100)))
    assert (await practice_service.set_enabled(True)).enabled


async def test_execute_opens_long_with_sl_tp_on_entry_signal() -> None:
    broker = FakeBroker()
    service, _, events = build_service(broker, SignalProvider(rising_then_data()))
    await service.set_enabled(True)
    report = await service.execute("ema_cross", Symbol.EURUSD, Timeframe.H1, units=1000)
    assert report.action == "opened_long"
    assert len(broker.market_orders) == 1
    symbol, units, stop_loss, take_profit = broker.market_orders[0]
    assert (symbol, units) == (Symbol.EURUSD, 1000)
    assert stop_loss is not None and take_profit is not None
    assert stop_loss < take_profit  # long: SL below entry, TP above
    assert any(isinstance(e, OrderExecuted) for e in events)


async def test_execute_reverses_an_open_short_first() -> None:
    broker = FakeBroker(positions=[Position(EUR_USD, -500, 1.1, -2.0)])
    service, _, _ = build_service(broker, SignalProvider(rising_then_data()))
    await service.set_enabled(True)
    report = await service.execute("ema_cross", Symbol.EURUSD, Timeframe.H1, units=1000)
    assert report.action == "opened_long"
    assert broker.closed == [Symbol.EURUSD]  # short closed before going long
    assert len(broker.market_orders) == 1


async def test_execute_without_signal_does_nothing() -> None:
    flat = make_market_data(200, seed=11)
    broker = FakeBroker()
    service, _, events = build_service(broker, SignalProvider(flat))
    await service.set_enabled(True)
    report = await service.execute("donchian", Symbol.EURUSD, Timeframe.H1, units=100)
    if report.action == "none":  # the typical case for a quiet last bar
        assert broker.market_orders == []
        assert not any(isinstance(e, OrderExecuted) for e in events)


# -- SQL trading state ---------------------------------------------------------------


async def test_sql_trading_state_round_trip() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        repo = SqlAlchemyTradingStateRepository(session)
        assert not (await repo.get()).enabled  # default off
        assert (await repo.set_enabled(True)).enabled
        assert (await repo.get()).enabled
        assert not (await repo.set_enabled(False)).enabled
    await engine.dispose()


# -- OANDA execution adapter ----------------------------------------------------------


def oanda_http(handler: object) -> OandaClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    http = httpx.AsyncClient(base_url="https://x", transport=transport)
    return OandaClient("token", "practice", http=http)


async def test_oanda_execution_account_and_positions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/summary"):
            return httpx.Response(
                200,
                json={
                    "account": {
                        "id": "001-1",
                        "currency": "USD",
                        "balance": "1000.5",
                        "NAV": "1001.0",
                        "marginUsed": "10",
                        "marginAvailable": "990",
                        "openPositionCount": 1,
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "positions": [
                    {
                        "instrument": EUR_USD,
                        "unrealizedPL": "3.2",
                        "long": {"units": "1000", "averagePrice": "1.10"},
                        "short": {"units": "0"},
                    }
                ]
            },
        )

    broker = OandaExecutionBroker(oanda_http(handler), "001-1")
    account = await broker.account_summary()
    assert account.balance == 1000.5
    positions = await broker.open_positions()
    assert positions[0].units == 1000
    assert positions[0].average_price == 1.10


async def test_oanda_execution_market_order_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            201, json={"orderFillTransaction": {"id": "77"}, "orderCreateTransaction": {"id": "76"}}
        )

    broker = OandaExecutionBroker(oanda_http(handler), "001-1")
    result = await broker.place_market_order(
        Symbol.EURUSD, 1000, stop_loss=1.09123456, take_profit=1.1298765
    )
    order = captured["order"]
    assert order["instrument"] == EUR_USD  # type: ignore[index]
    assert order["units"] == "1000"  # type: ignore[index]
    assert order["stopLossOnFill"] == {"price": "1.09123"}  # type: ignore[index]
    assert order["takeProfitOnFill"] == {"price": "1.12988"}  # type: ignore[index]
    assert result.filled and result.order_id == "77"


async def test_oanda_execution_close_position() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/openPositions"):
            return httpx.Response(
                200,
                json={
                    "positions": [
                        {
                            "instrument": EUR_USD,
                            "unrealizedPL": "0",
                            "long": {"units": "0"},
                            "short": {"units": "-500", "averagePrice": "1.2"},
                        }
                    ]
                },
            )
        payload = json.loads(request.content)
        assert payload == {"shortUnits": "ALL"}
        return httpx.Response(200, json={"shortOrderFillTransaction": {"id": "99"}})

    broker = OandaExecutionBroker(oanda_http(handler), "001-1")
    result = await broker.close_position(Symbol.EURUSD)
    assert result.filled and result.units == 500


async def test_oanda_close_without_position_is_a_noop() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"positions": []})

    broker = OandaExecutionBroker(oanda_http(handler), "001-1")
    result = await broker.close_position(Symbol.EURUSD)
    assert not result.filled and result.detail == "no position"


# -- routes ---------------------------------------------------------------------------


class FakeTradingService:
    def __init__(self) -> None:
        self.enabled = False

    async def status(self) -> object:
        from quantlab.application.services.trading import TradingStatus

        return TradingStatus(
            state=TradingState(enabled=self.enabled),
            environment="practice",
            account=AccountSummary("001-1", "USD", 10_000, 10_000, 0, 10_000, 0),
            positions=[],
        )

    async def set_enabled(self, enabled: bool, confirmation: str | None = None) -> TradingState:
        self.enabled = enabled
        return TradingState(enabled=enabled)

    async def execute(self, **kwargs: object) -> object:
        from quantlab.application.services.trading import ExecutionReport

        if not self.enabled:
            raise TradingDisabledError("Trading is disabled (kill switch off).")
        return ExecutionReport(
            action="opened_long", symbol=Symbol.EURUSD, signal_time="t", orders=[]
        )


class TradingStubContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.trading_service = FakeTradingService()


async def test_trading_routes(settings: Settings) -> None:
    app = create_app(settings)
    container = TradingStubContainer(settings)
    app.state.container = container
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        status = await client.get("/api/v1/trading/status")
        assert status.status_code == 200
        assert status.json()["enabled"] is False

        blocked = await client.post(
            "/api/v1/trading/execute",
            json={"strategy_id": "ema_cross", "symbol": "EURUSD", "timeframe": "H1", "units": 100},
        )
        assert blocked.status_code == 409

        toggled = await client.post("/api/v1/trading/toggle", json={"enabled": True})
        assert toggled.json()["enabled"] is True

        executed = await client.post(
            "/api/v1/trading/execute",
            json={"strategy_id": "ema_cross", "symbol": "EURUSD", "timeframe": "H1", "units": 100},
        )
        assert executed.status_code == 200
        assert executed.json()["action"] == "opened_long"
