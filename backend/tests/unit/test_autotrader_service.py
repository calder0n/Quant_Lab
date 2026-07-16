"""Tests for the auto-trader scheduling service."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest

from quantlab.application.ports import AutoTraderRepository, TradingStateRepository
from quantlab.application.services.autotrader import GLOBAL_OFF_MESSAGE, AutoTraderService
from quantlab.application.services.trading import ExecutionReport
from quantlab.domain.autotrader import AutoTrader
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.trading import TradingState
from quantlab.strategies.base import InvalidParameterError, ParamValue
from quantlab.strategies.registry import StrategyRegistry, UnknownStrategyError


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


class FakeTradingService:
    def __init__(self, action: str = "opened_long", raises: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.action = action
        self.raises = raises

    async def execute(
        self,
        strategy_id: str,
        symbol: Symbol,
        timeframe: Timeframe,
        units: float,
        params: dict[str, ParamValue] | None = None,
    ) -> ExecutionReport:
        self.calls.append(
            {"strategy": strategy_id, "symbol": symbol, "units": units, "params": params}
        )
        if self.raises is not None:
            raise self.raises
        return ExecutionReport(
            action=self.action, symbol=symbol, signal_time="2026-07-16 08:00:00+00:00", orders=[]
        )


def build(
    enabled_global: bool = True,
    trading: FakeTradingService | None = None,
) -> tuple[AutoTraderService, dict[uuid.UUID, AutoTrader], FakeTradingService, InMemoryState]:
    store: dict[uuid.UUID, AutoTrader] = {}
    state = InMemoryState(enabled_global)
    trading_service = trading or FakeTradingService()

    @asynccontextmanager
    async def repos() -> AsyncIterator[AutoTraderRepository]:
        yield InMemoryAutoTraderRepo(store)

    @asynccontextmanager
    async def states() -> AsyncIterator[TradingStateRepository]:
        yield state

    service = AutoTraderService(
        repositories=repos,
        states=states,
        trading_service=trading_service,  # type: ignore[arg-type]
        registry=StrategyRegistry().discover(),
    )
    return service, store, trading_service, state


NOW = datetime(2026, 7, 16, 9, 30, tzinfo=UTC)


# -- CRUD --------------------------------------------------------------------------


async def test_create_validates_strategy_and_params() -> None:
    service, store, _, _ = build()
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
    service, store, _, _ = build()
    at = await service.create("ema_cross", Symbol.EURUSD, Timeframe.H1, 1000.0)
    toggled = await service.set_enabled(at.id, True)
    assert toggled is not None and toggled.enabled
    assert store[at.id].last_bucket is None  # re-armed to act on current bar
    assert await service.set_enabled(uuid.uuid4(), True) is None
    assert await service.delete(at.id) is True
    assert await service.delete(at.id) is False


# -- scheduler ---------------------------------------------------------------------


async def test_run_tick_executes_enabled_assignment_once_per_bar() -> None:
    service, store, trading, _ = build()
    at = await service.create(
        "atr_breakout", Symbol.XAUUSD, Timeframe.H4, 1.0, {"breakout_atr": 1.7}
    )
    at.enabled = True
    store[at.id] = at

    await service.run_tick(NOW)
    assert len(trading.calls) == 1
    saved = store[at.id]
    assert saved.last_action == "opened_long"
    assert saved.last_bucket == int(NOW.timestamp() // Timeframe.H4.seconds)

    # same bar → no second execution
    await service.run_tick(NOW.replace(minute=45))
    assert len(trading.calls) == 1

    # next H4 bar → executes again
    later = NOW.replace(hour=13, minute=5)
    await service.run_tick(later)
    assert len(trading.calls) == 2


async def test_run_tick_skips_when_global_switch_off() -> None:
    service, store, trading, state = build(enabled_global=False)
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
    service, store, trading, _ = build()
    at = await service.create("rsi", Symbol.EURUSD, Timeframe.H1, 1000.0)  # enabled defaults False
    store[at.id] = at
    await service.run_tick(NOW)
    assert trading.calls == []


async def test_failed_execution_is_recorded_and_retries_next_tick() -> None:
    trading = FakeTradingService(raises=RuntimeError("broker down"))
    service, store, _, _ = build(trading=trading)
    at = await service.create("ema_cross", Symbol.EURUSD, Timeframe.H1, 1000.0)
    at.enabled = True
    store[at.id] = at

    await service.run_tick(NOW)
    assert "broker down" in (store[at.id].message or "")
    assert store[at.id].last_bucket is None  # not advanced → will retry
    # a later tick in the same bar retries (bucket was never set)
    await service.run_tick(NOW.replace(minute=59))
    assert len(trading.calls) == 2
