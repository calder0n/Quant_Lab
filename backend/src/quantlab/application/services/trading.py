"""Signal-driven order execution through the broker port.

Safety model: the kill switch is persisted and OFF by default; enabling it
while the configured credentials point at a live-money environment requires
the typed confirmation ``TRADE-LIVE``. The platform never enables itself.
"""

import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from quantlab.application.event_bus import EventBus
from quantlab.application.ports import (
    ExecutionBroker,
    MarketDataProvider,
    TradingStateRepository,
)
from quantlab.domain.broker import BrokerCredentials
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.trading import (
    LIVE_CONFIRMATION,
    AccountSummary,
    LiveConfirmationError,
    OrderExecuted,
    OrderResult,
    Position,
    TradingDisabledError,
    TradingState,
)
from quantlab.strategies.base import ParamValue
from quantlab.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)

TradingStateRepositoryFactory = Callable[[], AbstractAsyncContextManager[TradingStateRepository]]

SIGNAL_LOOKBACK_BARS = 400


@dataclass(frozen=True)
class TradingStatus:
    state: TradingState
    environment: str
    account: AccountSummary | None
    positions: list[Position]
    detail: str | None = None


@dataclass(frozen=True)
class ExecutionReport:
    action: str  # opened_long | opened_short | closed | none
    symbol: Symbol
    signal_time: str
    orders: list[OrderResult]


class TradingService:
    """Account visibility, kill switch and one-shot signal execution."""

    def __init__(
        self,
        states: TradingStateRepositoryFactory,
        broker_factory: Callable[[], Awaitable[ExecutionBroker]],
        credentials_resolver: Callable[[], Awaitable[BrokerCredentials]],
        registry: StrategyRegistry,
        market_data: Callable[[], Awaitable[MarketDataProvider]],
        event_bus: EventBus,
    ) -> None:
        self._states = states
        self._broker_factory = broker_factory
        self._credentials = credentials_resolver
        self._registry = registry
        self._market_data = market_data
        self._event_bus = event_bus

    async def status(self) -> TradingStatus:
        async with self._states() as repo:
            state = await repo.get()
        credentials = await self._credentials()
        if not credentials.configured or not credentials.account_id:
            return TradingStatus(
                state=state,
                environment=credentials.environment,
                account=None,
                positions=[],
                detail="Configure OANDA credentials (token + account id) first.",
            )
        try:
            broker = await self._broker_factory()
            account = await broker.account_summary()
            positions = await broker.open_positions()
        except Exception as exc:
            return TradingStatus(
                state=state,
                environment=credentials.environment,
                account=None,
                positions=[],
                detail=f"Broker unreachable: {exc}",
            )
        return TradingStatus(
            state=state, environment=credentials.environment, account=account, positions=positions
        )

    async def set_enabled(self, enabled: bool, confirmation: str | None = None) -> TradingState:
        credentials = await self._credentials()
        if enabled and credentials.environment == "live" and confirmation != LIVE_CONFIRMATION:
            raise LiveConfirmationError(
                f"Enabling LIVE trading requires confirmation {LIVE_CONFIRMATION!r}."
            )
        async with self._states() as repo:
            state = await repo.set_enabled(enabled)
        logger.warning(
            "Trading %s (%s environment)",
            "ENABLED" if enabled else "disabled",
            credentials.environment,
        )
        return state

    async def execute(
        self,
        strategy_id: str,
        symbol: Symbol,
        timeframe: Timeframe,
        units: float,
        params: dict[str, ParamValue] | None = None,
        data: pd.DataFrame | None = None,
    ) -> ExecutionReport:
        """Evaluate the strategy on broker candles and act on the last closed bar.

        ``data`` may be pre-fetched by the caller (the auto-trader fetches once
        to gate on the candle-close time and reuses it here); otherwise fresh
        candles are pulled from the broker.
        """
        async with self._states() as repo:
            state = await repo.get()
        if not state.enabled:
            raise TradingDisabledError("Trading is disabled (kill switch off).")

        if data is None:
            provider = await self._market_data()
            end = datetime.now(UTC)
            start = end - SIGNAL_LOOKBACK_BARS * timeframe.delta
            data = await provider.fetch_candles(symbol, timeframe, start, end)
        if len(data) < 50:
            raise ValueError(f"Only {len(data)} fresh bars available for {symbol} {timeframe}.")

        strategy = self._registry.create(strategy_id, params)
        signals = strategy.generate_signals(data)
        plan = strategy.generate_orders(data, signals)
        last = signals.iloc[-1]
        close = float(data["close"].iloc[-1])
        signal_time = str(data.index[-1])

        broker = await self._broker_factory()
        positions = await broker.open_positions()
        current_units = 0.0
        from quantlab.infrastructure.brokers.oanda.market_data import INSTRUMENTS

        instrument = INSTRUMENTS[symbol]
        for position in positions:
            if position.symbol == instrument:
                current_units = position.units

        sl_pct = float(plan.sl_pct.iloc[-1]) if plan.sl_pct is not None else None
        tp_pct = float(plan.tp_pct.iloc[-1]) if plan.tp_pct is not None else None
        orders: list[OrderResult] = []
        action = "none"

        if bool(last["long_entry"]) and current_units <= 0:
            if current_units < 0:
                orders.append(await broker.close_position(symbol))
            orders.append(
                await broker.place_market_order(
                    symbol,
                    abs(units),
                    stop_loss=close * (1 - sl_pct) if sl_pct else None,
                    take_profit=close * (1 + tp_pct) if tp_pct else None,
                )
            )
            action = "opened_long"
        elif bool(last["short_entry"]) and current_units >= 0:
            if current_units > 0:
                orders.append(await broker.close_position(symbol))
            orders.append(
                await broker.place_market_order(
                    symbol,
                    -abs(units),
                    stop_loss=close * (1 + sl_pct) if sl_pct else None,
                    take_profit=close * (1 - tp_pct) if tp_pct else None,
                )
            )
            action = "opened_short"
        elif (bool(last["long_exit"]) and current_units > 0) or (
            bool(last["short_exit"]) and current_units < 0
        ):
            orders.append(await broker.close_position(symbol))
            action = "closed"

        if action != "none":
            logger.warning("Executed %s %s via %s (units=%s)", action, symbol, strategy_id, units)
            await self._event_bus.publish(
                OrderExecuted(symbol=symbol, action=action, units=units, strategy_id=strategy_id)
            )
        return ExecutionReport(action=action, symbol=symbol, signal_time=signal_time, orders=orders)
