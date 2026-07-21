"""SQLAlchemy implementation of the ``ValidationRepository`` port."""

import uuid
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantlab.application.ports import ValidationRepository
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.optimization import StudyStatus
from quantlab.domain.validation import ValidationKind, ValidationRun
from quantlab.infrastructure.db.models.validation import ValidationRunRecord
from quantlab.strategies.base import ParamValue


def _to_entity(record: ValidationRunRecord) -> ValidationRun:
    return ValidationRun(
        id=record.id,
        kind=ValidationKind(record.kind),
        strategy_id=record.strategy_id,
        symbol=Symbol(record.symbol),
        timeframe=Timeframe(record.timeframe),
        status=StudyStatus(record.status),
        params=cast(dict[str, ParamValue] | None, record.params),
        config=record.config or {},
        result=record.result,
        message=record.message,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _apply(record: ValidationRunRecord, run: ValidationRun) -> None:
    record.kind = run.kind.value
    record.strategy_id = run.strategy_id
    record.symbol = run.symbol.value
    record.timeframe = run.timeframe.value
    record.status = run.status.value
    record.params = run.params
    record.config = run.config
    record.result = run.result
    record.message = run.message


class SqlAlchemyValidationRepository(ValidationRepository):
    """Validation runs persisted in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, run: ValidationRun) -> ValidationRun:
        record = ValidationRunRecord(id=run.id)
        _apply(record, run)
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return _to_entity(record)

    async def get(self, run_id: uuid.UUID) -> ValidationRun | None:
        record = await self._session.get(ValidationRunRecord, run_id)
        return _to_entity(record) if record is not None else None

    async def list_all(self) -> list[ValidationRun]:
        result = await self._session.execute(
            select(ValidationRunRecord).order_by(ValidationRunRecord.created_at.desc())
        )
        return [_to_entity(record) for record in result.scalars()]

    async def update(self, run: ValidationRun) -> ValidationRun:
        record = await self._session.get(ValidationRunRecord, run.id)
        if record is None:
            return await self.create(run)
        _apply(record, run)
        await self._session.flush()
        await self._session.refresh(record)
        return _to_entity(record)
