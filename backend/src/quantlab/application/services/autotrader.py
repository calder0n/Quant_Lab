"""Automated-trading orchestration.

Owns the CRUD of auto-trading assignments and the per-tick scheduler used by
the dedicated worker. Scheduling is deduplicated by *timeframe bucket*: at time
``t`` the bucket is ``floor(t / timeframe_seconds)``, so each assignment acts at
most once per bar. The actual reading of fresh OANDA candles, signal evaluation
and order placement is delegated to :class:`TradingService`, so the auto-trader
reuses the exact same execution path (kill switch, SL/TP, reversals) as a manual
run — it only adds scheduling and persistence.
"""

import logging
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import datetime

from quantlab.application.ports import AutoTraderRepository, TradingStateRepository
from quantlab.application.services.trading import TradingService
from quantlab.domain.autotrader import AutoTrader
from quantlab.domain.market import Symbol, Timeframe
from quantlab.strategies.base import ParamValue
from quantlab.strategies.registry import StrategyRegistry, UnknownStrategyError

logger = logging.getLogger(__name__)

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
    ) -> None:
        self._repositories = repositories
        self._states = states
        self._trading = trading_service
        self._registry = registry

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
                auto_trader.last_bucket = None  # act on the current bar right away
            return await repo.update(auto_trader)

    async def delete(self, auto_trader_id: uuid.UUID) -> bool:
        async with self._repositories() as repo:
            if await repo.get(auto_trader_id) is None:
                return False
            await repo.delete(auto_trader_id)
            return True

    # -- scheduler -------------------------------------------------------------

    async def run_tick(self, now: datetime) -> list[AutoTrader]:
        """Process every enabled assignment whose timeframe bar has advanced.

        Never raises: per-assignment failures are recorded on the row so the
        dashboard can surface them while the loop keeps running.
        """
        async with self._states() as state_repo:
            globally_enabled = (await state_repo.get()).enabled
        async with self._repositories() as repo:
            due = await repo.list_enabled()

        processed: list[AutoTrader] = []
        for auto_trader in due:
            bucket = int(now.timestamp() // auto_trader.timeframe.seconds)
            if auto_trader.last_bucket == bucket:
                continue  # already acted on this bar
            if not globally_enabled:
                if auto_trader.message != GLOBAL_OFF_MESSAGE:
                    auto_trader.message = GLOBAL_OFF_MESSAGE
                    await self._save(auto_trader)
                continue
            await self._run_one(auto_trader, bucket, now)
            processed.append(auto_trader)
        return processed

    async def _run_one(self, auto_trader: AutoTrader, bucket: int, now: datetime) -> None:
        try:
            report = await self._trading.execute(
                strategy_id=auto_trader.strategy_id,
                symbol=auto_trader.symbol,
                timeframe=auto_trader.timeframe,
                units=auto_trader.units,
                params=auto_trader.params,
            )
            auto_trader.last_bucket = bucket
            auto_trader.last_run = now
            auto_trader.last_signal_time = report.signal_time
            auto_trader.last_action = report.action
            auto_trader.message = None
            logger.info(
                "AutoTrader %s %s %s -> %s",
                auto_trader.strategy_id,
                auto_trader.symbol,
                auto_trader.timeframe,
                report.action,
            )
        except UnknownStrategyError as exc:
            auto_trader.message = f"Unknown strategy: {exc.args[0]}"
            logger.exception("AutoTrader %s misconfigured", auto_trader.id)
        except Exception as exc:
            # Transient (e.g. broker unreachable): keep last_bucket so it retries
            # on the next tick rather than waiting a whole bar.
            auto_trader.message = f"{type(exc).__name__}: {exc}"
            logger.exception("AutoTrader %s failed", auto_trader.id)
        await self._save(auto_trader)

    async def _save(self, auto_trader: AutoTrader) -> None:
        async with self._repositories() as repo:
            await repo.update(auto_trader)
