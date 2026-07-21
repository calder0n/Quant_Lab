"""SQLAlchemy implementation of the trade history port."""

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantlab.application.ports import TradeHistoryRepository
from quantlab.domain.market import Symbol
from quantlab.domain.trading import TradeRecord
from quantlab.infrastructure.db.models.trade_history import TradeHistoryRecord
from quantlab.strategies.base import ParamValue


def _to_entity(record: TradeHistoryRecord) -> TradeRecord:
    return TradeRecord(
        id=record.id,
        strategy_id=record.strategy_id,
        symbol=Symbol(record.symbol),
        timeframe=record.timeframe,
        action=record.action,
        source=record.source,
        units=record.units,
        entry_price=record.entry_price,
        sl_price=record.sl_price,
        tp_price=record.tp_price,
        trailing_distance=record.trailing_distance,
        realized_pl=record.realized_pl,
        order_id=record.order_id,
        filled=record.filled,
        detail=record.detail,
        signal_time=record.signal_time,
        params=cast(dict[str, ParamValue], record.params or {}),
        executed_at=record.executed_at,
    )


class SqlAlchemyTradeHistoryRepository(TradeHistoryRepository):
    """Executed-order history persisted in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, record: TradeRecord) -> TradeRecord:
        row = TradeHistoryRecord(
            id=record.id,
            strategy_id=record.strategy_id,
            symbol=record.symbol.value,
            timeframe=record.timeframe,
            action=record.action,
            source=record.source,
            units=record.units,
            entry_price=record.entry_price,
            sl_price=record.sl_price,
            tp_price=record.tp_price,
            trailing_distance=record.trailing_distance,
            realized_pl=record.realized_pl,
            order_id=record.order_id,
            filled=record.filled,
            detail=record.detail,
            signal_time=record.signal_time,
            params=dict(record.params),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_entity(row)

    async def list_recent(
        self, limit: int = 100, strategy_id: str | None = None
    ) -> list[TradeRecord]:
        query = select(TradeHistoryRecord).order_by(TradeHistoryRecord.executed_at.desc())
        if strategy_id is not None:
            query = query.where(TradeHistoryRecord.strategy_id == strategy_id)
        result = await self._session.execute(query.limit(limit))
        return [_to_entity(row) for row in result.scalars()]

    async def realized_pnl_by_assignment(
        self, source: str | None = None
    ) -> dict[tuple[str, str, str], float]:
        r = TradeHistoryRecord
        query = (
            select(r.strategy_id, r.symbol, r.timeframe, func.sum(r.realized_pl))
            .where(r.realized_pl.is_not(None))
            .group_by(r.strategy_id, r.symbol, r.timeframe)
        )
        if source is not None:
            query = query.where(r.source == source)
        result = await self._session.execute(query)
        return {
            (strategy_id, symbol, timeframe): float(total)
            for strategy_id, symbol, timeframe, total in result.all()
        }
