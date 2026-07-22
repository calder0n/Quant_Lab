"""SQLAlchemy implementation of the trade history port."""

from datetime import UTC
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
        broker_trade_id=record.broker_trade_id,
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
            broker_trade_id=record.broker_trade_id,
            params=dict(record.params),
            # Honor an explicit time (e.g. a broker close's own timestamp);
            # otherwise the column defaults to now() at insert.
            **({"executed_at": record.executed_at} if record.executed_at is not None else {}),
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

    async def realized_pnl_by_day(self) -> dict[str, float]:
        # Aggregated in Python (portable across Postgres/SQLite) over UTC dates.
        result = await self._session.execute(
            select(TradeHistoryRecord.executed_at, TradeHistoryRecord.realized_pl).where(
                TradeHistoryRecord.realized_pl.is_not(None)
            )
        )
        totals: dict[str, float] = {}
        for executed_at, pl in result.all():
            if executed_at is None or pl is None:
                continue
            moment = executed_at if executed_at.tzinfo else executed_at.replace(tzinfo=UTC)
            day = moment.astimezone(UTC).date().isoformat()
            totals[day] = round(totals.get(day, 0.0) + float(pl), 2)
        return totals

    async def open_for_trade_id(self, broker_trade_id: str) -> TradeRecord | None:
        result = await self._session.execute(
            select(TradeHistoryRecord)
            .where(TradeHistoryRecord.broker_trade_id == broker_trade_id)
            .where(TradeHistoryRecord.action.in_(("opened_long", "opened_short")))
            .order_by(TradeHistoryRecord.executed_at.asc())
            .limit(1)
        )
        row = result.scalars().first()
        return _to_entity(row) if row is not None else None

    async def exists_with_order_id(self, order_id: str) -> bool:
        result = await self._session.execute(
            select(TradeHistoryRecord.id).where(TradeHistoryRecord.order_id == order_id).limit(1)
        )
        return result.first() is not None
