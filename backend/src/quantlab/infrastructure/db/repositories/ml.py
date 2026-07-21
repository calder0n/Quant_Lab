"""SQLAlchemy implementation of the ``MlModelRepository`` port."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from quantlab.application.ports import MlModelRepository
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.ml import MlModel, ModelKind
from quantlab.domain.optimization import StudyStatus
from quantlab.infrastructure.db.models.ml import MlModelRecord


def _to_entity(record: MlModelRecord) -> MlModel:
    return MlModel(
        id=record.id,
        kind=ModelKind(record.kind),
        target=record.target,
        algorithm=record.algorithm,
        symbol=Symbol(record.symbol),
        timeframe=Timeframe(record.timeframe),
        status=StudyStatus(record.status),
        config=record.config or {},
        metrics=record.metrics,
        artifact_path=record.artifact_path,
        message=record.message,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _apply(record: MlModelRecord, model: MlModel) -> None:
    record.kind = model.kind.value
    record.target = model.target
    record.algorithm = model.algorithm
    record.symbol = model.symbol.value
    record.timeframe = model.timeframe.value
    record.status = model.status.value
    record.config = model.config
    record.metrics = model.metrics
    record.artifact_path = model.artifact_path
    record.message = model.message


class SqlAlchemyMlModelRepository(MlModelRepository):
    """ML/RL model registry persisted in PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, model: MlModel) -> MlModel:
        record = MlModelRecord(id=model.id)
        _apply(record, model)
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return _to_entity(record)

    async def get(self, model_id: uuid.UUID) -> MlModel | None:
        record = await self._session.get(MlModelRecord, model_id)
        return _to_entity(record) if record is not None else None

    async def list_all(self) -> list[MlModel]:
        result = await self._session.execute(
            select(MlModelRecord).order_by(MlModelRecord.created_at.desc())
        )
        return [_to_entity(record) for record in result.scalars()]

    async def update(self, model: MlModel) -> MlModel:
        record = await self._session.get(MlModelRecord, model.id)
        if record is None:
            return await self.create(model)
        _apply(record, model)
        await self._session.flush()
        await self._session.refresh(record)
        return _to_entity(record)
