"""Tests for the auto-trader scheduling service."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pandas as pd
import pytest

from quantlab.application.ports import (
    AutoTraderRepository,
    MarketDataProvider,
    TradingStateRepository,
)
from quantlab.application.services.autotrader import GLOBAL_OFF_MESSAGE, AutoTraderService
from quantlab.application.services.trading import ExecutionReport
from quantlab.domain.autotrader import AutoTrader
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.trading import TradingState
from quantlab.strategies.base import InvalidParameterError, ParamValue
from quantlab.strategies.registry import StrategyRegistry, UnknownStrategyError
from tests.factories import make_market_data


class InMemoryAutoTraderRepo(AutoTraderRepository):
    def __init__(self, store: dict[uuid.UUID, AutoTrader]) -> None:
        self.store = store

    async def create(self, auto_trader: AutoTrader) -> AutoTrader:
        self.store[auto_trader.id] = auto_trader
        return auto_trader

    async def get(self, auto_trader_id: uuid.UUID) -> AutoTrader | None:
        return self.store.get(auto_trader_id)

    async def list_all(self) -> list[AutoTrader]:
        return list(self.store.values())

    async def list_enabled(self) -> list[AutoTrader]:
        return [a for a in self.store.values() if a.enabled]

    async def update(self, auto_trader: AutoTrader) -> AutoTrader:
        self.store[auto_trader.id] = auto_trader
        return auto_trader

    async def delete(self, auto_trader_id: uuid.UUID) -> None:
        self.store.pop(auto_trader_id, None)


class InMemoryState(TradingStateRepository):
    def __init__(self, enabled: bool) -> None:
        self.state = TradingState(enabled=enabled)

    async def get(self) -> TradingState:
        return self.state

    async def set_enabled(self, enabled: bool) -> TradingState:
        self.state = TradingState(enabled=enabled)
        return self.state


class FakeProvider(MarketDataProvider):
    """Serves candles whose latest bar advances only when ``new_bar`` is called."""

    def __init__(self) -> None:
        self.bars = 100

    @property
    def name(self) -> str:
        return "fake"

    async def fetch_candles(
        self, symbol: Symbol, timeframe: Timeframe, start: datetime, end: datetime
    ) -> pd.DataFrame:
        return make_market_data(self.bars, timeframe=timeframe)

    def new_bar(self) -> None:
        self.bars += 1  # a later last-bar timestamp → a "new closed bar"


class FakeTradingService:
    def __init__(self, action: str = "opened_long", raises: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.action = action
        self.raises = raises
        self.reconcile_calls = 0

    async def reconcile_broker_closes(self) -> int:
        self.reconcile_calls += 1
        return 0

    async def execute(
        self,
        strategy_id: str,
        symbol: Symbol,
        timeframe: Timeframe,
        units: float,
        params: dict[str, ParamValue] | None = None,
        data: pd.DataFrame | None = None,
        source: str = "manual",
        ml_model_id: str | None = None,
    ) -> ExecutionReport:
        assert source == "autotrader"  # the worker must label its own executions
        self.calls.append(
            {"strategy": strategy_id, "symbol": symbol, "units": units, "params": params}
        )
        if self.raises is not None:
            raise self.raises
        signal_time = str(data.index[-1]) if data is not None else "2026-07-16 08:00:00+00:00"
        return ExecutionReport(
            action=self.action, symbol=symbol, signal_time=signal_time, orders=[]
        )


def build(
    enabled_global: bool = True,
    trading: FakeTradingService | None = None,
) -> tuple[
    AutoTraderService, dict[uuid.UUID, AutoTrader], FakeTradingService, InMemoryState, FakeProvider
]:
    store: dict[uuid.UUID, AutoTrader] = {}
    state = InMemoryState(enabled_global)
    trading_service = trading or FakeTradingService()
    provider = FakeProvider()

    @asynccontextmanager
    async def repos() -> AsyncIterator[AutoTraderRepository]:
        yield InMemoryAutoTraderRepo(store)

    @asynccontextmanager
    async def states() -> AsyncIterator[TradingStateRepository]:
        yield state

    async def market_data() -> MarketDataProvider:
        return provider

    service = AutoTraderService(
        repositories=repos,
        states=states,
        trading_service=trading_service,  # type: ignore[arg-type]
        registry=StrategyRegistry().discover(),
        market_data=market_data,
    )
    return service, store, trading_service, state, provider


NOW = datetime(2026, 7, 16, 9, 30, tzinfo=UTC)


# -- CRUD --------------------------------------------------------------------------


async def test_create_validates_strategy_and_params() -> None:
    service, store, _, _, _ = build()
    at = await service.create(
        "atr_breakout", Symbol.XAUUSD, Timeframe.H4, 1.0, {"breakout_atr": 1.7}
    )
    assert at.id in store
    assert at.enabled is False  # starts disabled
    with pytest.raises(UnknownStrategyError):
        await service.create("nope", Symbol.XAUUSD, Timeframe.H4, 1.0)
    with pytest.raises(InvalidParameterError):
        await service.create("atr_breakout", Symbol.XAUUSD, Timeframe.H4, 1.0, {"bad": 1})


async def test_toggle_and_delete() -> None:
    service, store, _, _, _ = build()
    at = await service.create("ema_cross", Symbol.EURUSD, Timeframe.H1, 1000.0)
    toggled = await service.set_enabled(at.id, True)
    assert toggled is not None and toggled.enabled
    assert store[at.id].last_signal_time is None  # re-armed to act on current bar
    assert await service.set_enabled(uuid.uuid4(), True) is None
    assert await service.delete(at.id) is True
    assert await service.delete(at.id) is False


# -- scheduler ---------------------------------------------------------------------


async def test_run_tick_executes_only_when_a_new_bar_closes() -> None:
    service, store, trading, _, provider = build()
    at = await service.create(
        "atr_breakout", Symbol.XAUUSD, Timeframe.H4, 1.0, {"breakout_atr": 1.7}
    )
    at.enabled = True
    store[at.id] = at

    await service.run_tick(NOW)
    assert len(trading.calls) == 1
    saved = store[at.id]
    assert saved.last_action == "opened_long"
    assert saved.last_signal_time is not None

    # polling again with no new closed bar → no second execution
    await service.run_tick(NOW)
    await service.run_tick(NOW)
    assert len(trading.calls) == 1

    # a fresh closed bar on the broker → executes again on the next poll
    provider.new_bar()
    await service.run_tick(NOW)
    assert len(trading.calls) == 2


async def test_run_tick_skips_when_global_switch_off() -> None:
    service, store, trading, state, _ = build(enabled_global=False)
    at = await service.create("ema_cross", Symbol.EURUSD, Timeframe.H1, 1000.0)
    at.enabled = True
    store[at.id] = at

    await service.run_tick(NOW)
    assert trading.calls == []
    assert store[at.id].message == GLOBAL_OFF_MESSAGE

    # turning it on lets the next tick execute
    state.state = TradingState(enabled=True)
    await service.run_tick(NOW)
    assert len(trading.calls) == 1


async def test_run_tick_ignores_disabled_assignments() -> None:
    service, store, trading, _, _ = build()
    at = await service.create("rsi", Symbol.EURUSD, Timeframe.H1, 1000.0)  # enabled defaults False
    store[at.id] = at
    await service.run_tick(NOW)
    assert trading.calls == []


async def test_run_tick_emits_a_heartbeat(caplog: pytest.LogCaptureFixture) -> None:
    service, store, _, _, _ = build()
    at = await service.create("ema_cross", Symbol.EURUSD, Timeframe.H1, 1000.0)
    at.enabled = True
    store[at.id] = at
    with caplog.at_level("INFO", logger="autotrader.heartbeat"):
        await service.run_tick(NOW)
    assert any("kill-switch ON | 1 enabled, 1 evaluated a new bar" in m for m in caplog.messages)


async def test_failed_execution_is_recorded_and_retries_next_tick() -> None:
    trading = FakeTradingService(raises=RuntimeError("broker down"))
    service, store, _, _, _ = build(trading=trading)
    at = await service.create("ema_cross", Symbol.EURUSD, Timeframe.H1, 1000.0)
    at.enabled = True
    store[at.id] = at

    await service.run_tick(NOW)
    assert "broker down" in (store[at.id].message or "")
    assert store[at.id].last_signal_time is None  # untouched → same bar retried
    await service.run_tick(NOW)
    assert len(trading.calls) == 2
