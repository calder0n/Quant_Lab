"""SQLAlchemy implementation of the ``AutoTraderRepository`` port."""

import uuid
from typing import cast

from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantlab.application.ports import AutoTraderRepository
from quantlab.domain.autotrader import AutoTrader
from quantlab.domain.market import Symbol, Timeframe
from quantlab.infrastructure.db.models.autotrader import AutoTraderRecord
from quantlab.strategies.base import ParamValue


def _to_entity(record: AutoTraderRecord) -> AutoTrader:
    return AutoTrader(
        id=record.id,
        strategy_id=record.strategy_id,
        symbol=Symbol(record.symbol),
        timeframe=Timeframe(record.timeframe),
        units=record.units,
        params=cast(dict[str, ParamValue], record.params or {}),
        enabled=record.enabled,
        last_bucket=record.last_bucket,
        last_run=record.last_run,
        last_signal_time=record.last_signal_time,
        last_action=record.last_action,
        message=record.message,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _apply(record: AutoTraderRecord, at: AutoTrader) -> None:
    record.strategy_id = at.strategy_id
    record.symbol = at.symbol.value
    record.timeframe = at.timeframe.value
    record.units = at.units
    record.params = at.params
    record.enabled = at.enabled
    record.last_bucket = at.last_bucket
    record.last_run = at.last_run
    record.last_signal_time = at.last_signal_time
    record.last_action = at.last_action
    record.message = at.message


class SqlAlchemyAutoTraderRepository(AutoTraderRepository):
    """Automated-trading assignments persisted in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, auto_trader: AutoTrader) -> AutoTrader:
        record = AutoTraderRecord(id=auto_trader.id)
        _apply(record, auto_trader)
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return _to_entity(record)

    async def get(self, auto_trader_id: uuid.UUID) -> AutoTrader | None:
        record = await self._session.get(AutoTraderRecord, auto_trader_id)
        return _to_entity(record) if record is not None else None

    async def list_all(self) -> list[AutoTrader]:
        result = await self._session.execute(
            select(AutoTraderRecord).order_by(AutoTraderRecord.created_at.desc())
        )
        return [_to_entity(record) for record in result.scalars()]

    async def list_enabled(self) -> list[AutoTrader]:
        result = await self._session.execute(
            select(AutoTraderRecord).where(AutoTraderRecord.enabled.is_(True))
        )
        return [_to_entity(record) for record in result.scalars()]

    async def update(self, auto_trader: AutoTrader) -> AutoTrader:
        record = await self._session.get(AutoTraderRecord, auto_trader.id)
        if record is None:
            return await self.create(auto_trader)
        _apply(record, auto_trader)
        await self._session.flush()
        await self._session.refresh(record)
        return _to_entity(record)

    async def delete(self, auto_trader_id: uuid.UUID) -> None:
        await self._session.execute(
            sql_delete(AutoTraderRecord).where(AutoTraderRecord.id == auto_trader_id)
        )
