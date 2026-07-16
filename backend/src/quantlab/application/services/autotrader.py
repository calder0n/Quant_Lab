"""Automated-trading orchestration.

Owns the CRUD of auto-trading assignments and the per-tick scheduler used by the
dedicated worker. The worker polls at a fine cadence (seconds); each poll fetches
the latest OANDA candles once and acts **only when a new bar has closed** — i.e.
the moment the strategy's timeframe bar completes on the broker's own grid — so
entries fire within one poll of the real candle close, never mid-bar and never on
a sliding window. Execution itself (kill switch, SL/TP, reversals) is delegated
to :class:`TradingService`, reusing the exact path of a manual run.
"""

import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime

from quantlab.application.ports import (
    AutoTraderRepository,
    MarketDataProvider,
    TradingStateRepository,
)
from quantlab.application.services.trading import SIGNAL_LOOKBACK_BARS, TradingService
from quantlab.domain.autotrader import AutoTrader
from quantlab.domain.market import Symbol, Timeframe
from quantlab.strategies.base import ParamValue
from quantlab.strategies.registry import StrategyRegistry, UnknownStrategyError

logger = logging.getLogger(__name__)
# Heartbeat lives outside the ``quantlab`` logger tree so it prints to the
# worker's stdout every tick without flooding the capped dashboard log buffer.
heartbeat = logging.getLogger("autotrader.heartbeat")

AutoTraderRepositoryFactory = Callable[[], AbstractAsyncContextManager[AutoTraderRepository]]
TradingStateRepositoryFactory = Callable[[], AbstractAsyncContextManager[TradingStateRepository]]

GLOBAL_OFF_MESSAGE = "Global trading is off — enable the kill switch in the Trading panel."


class AutoTraderService:
    """Manages auto-trading assignments and runs their scheduled executions."""

    def __init__(
        self,
        repositories: AutoTraderRepositoryFactory,
        states: TradingStateRepositoryFactory,
        trading_service: TradingService,
        registry: StrategyRegistry,
        market_data: Callable[[], Awaitable[MarketDataProvider]],
    ) -> None:
        self._repositories = repositories
        self._states = states
        self._trading = trading_service
        self._registry = registry
        self._market_data = market_data

    # -- CRUD ------------------------------------------------------------------

    async def create(
        self,
        strategy_id: str,
        symbol: Symbol,
        timeframe: Timeframe,
        units: float,
        params: dict[str, ParamValue] | None = None,
    ) -> AutoTrader:
        """Register an assignment; validates the strategy and its parameters."""
        self._registry.create(strategy_id, params)  # raises on unknown id / bad params
        auto_trader = AutoTrader(
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            units=units,
            params=dict(params or {}),
        )
        async with self._repositories() as repo:
            return await repo.create(auto_trader)

    async def list_all(self) -> list[AutoTrader]:
        async with self._repositories() as repo:
            return await repo.list_all()

    async def set_enabled(self, auto_trader_id: uuid.UUID, enabled: bool) -> AutoTrader | None:
        async with self._repositories() as repo:
            auto_trader = await repo.get(auto_trader_id)
            if auto_trader is None:
                return None
            auto_trader.enabled = enabled
            if enabled:
                auto_trader.message = None
                auto_trader.last_signal_time = None  # act on the current bar right away
            return await repo.update(auto_trader)

    async def delete(self, auto_trader_id: uuid.UUID) -> bool:
        async with self._repositories() as repo:
            if await repo.get(auto_trader_id) is None:
                return False
            await repo.delete(auto_trader_id)
            return True

    # -- scheduler -------------------------------------------------------------

    async def run_tick(self, now: datetime) -> list[AutoTrader]:
        """Process every enabled assignment whose latest bar has just closed.

        Never raises: per-assignment failures are recorded on the row so the
        dashboard can surface them while the loop keeps running.
        """
        async with self._states() as state_repo:
            globally_enabled = (await state_repo.get()).enabled
        async with self._repositories() as repo:
            due = await repo.list_enabled()

        processed: list[AutoTrader] = []
        for auto_trader in due:
            if not globally_enabled:
                if auto_trader.message != GLOBAL_OFF_MESSAGE:
                    auto_trader.message = GLOBAL_OFF_MESSAGE
                    await self._save(auto_trader)
                continue
            if await self._run_one(auto_trader, now):
                processed.append(auto_trader)

        # "evaluated" = assignments whose new bar we assessed this tick (an order is
        # only placed when that bar carries a signal — see the per-assignment log).
        heartbeat.info(
            "%s | kill-switch %s | %d enabled, %d evaluated a new bar this tick",
            now.isoformat(timespec="seconds"),
            "ON" if globally_enabled else "OFF",
            len(due),
            len(processed),
        )
        return processed

    async def _run_one(self, auto_trader: AutoTrader, now: datetime) -> bool:
        """Act only if the broker's latest *closed* bar is newer than the last one
        we already processed for this assignment. Returns whether an order pass ran.
        """
        try:
            provider = await self._market_data()
            start = now - SIGNAL_LOOKBACK_BARS * auto_trader.timeframe.delta
            data = await provider.fetch_candles(
                auto_trader.symbol, auto_trader.timeframe, start, now
            )
            if len(data) == 0:
                return False
            last_bar = str(data.index[-1])
            if last_bar == auto_trader.last_signal_time:
                return False  # no new closed bar since we last acted

            report = await self._trading.execute(
                strategy_id=auto_trader.strategy_id,
                symbol=auto_trader.symbol,
                timeframe=auto_trader.timeframe,
                units=auto_trader.units,
                params=auto_trader.params,
                data=data,
            )
            auto_trader.last_run = now
            auto_trader.last_signal_time = report.signal_time
            auto_trader.last_action = report.action
            auto_trader.message = None
            logger.info(
                "AutoTrader %s %s %s bar %s -> %s",
                auto_trader.strategy_id,
                auto_trader.symbol,
                auto_trader.timeframe,
                report.signal_time,
                report.action,
            )
        except UnknownStrategyError as exc:
            auto_trader.message = f"Unknown strategy: {exc.args[0]}"
            logger.exception("AutoTrader %s misconfigured", auto_trader.id)
        except Exception as exc:
            # Transient (e.g. broker unreachable): last_signal_time is untouched,
            # so the same bar is retried on the next tick.
            auto_trader.message = f"{type(exc).__name__}: {exc}"
            logger.exception("AutoTrader %s failed", auto_trader.id)
        await self._save(auto_trader)
        return True

    async def _save(self, auto_trader: AutoTrader) -> None:
        async with self._repositories() as repo:
            await repo.update(auto_trader)
