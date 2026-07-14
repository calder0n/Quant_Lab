"""SQLAlchemy implementation of the ``BrokerSettingsRepository`` port."""

from typing import cast

from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from quantlab.application.ports import BrokerSettingsRepository
from quantlab.domain.broker import BrokerCredentials, BrokerEnvironment
from quantlab.infrastructure.db.models.broker_settings import BrokerSettingsRecord


def _to_entity(record: BrokerSettingsRecord) -> BrokerCredentials:
    return BrokerCredentials(
        broker=record.broker,
        api_token=record.api_token,
        account_id=record.account_id,
        environment=cast(BrokerEnvironment, record.environment),
        updated_at=record.updated_at,
    )


class SqlAlchemyBrokerSettingsRepository(BrokerSettingsRepository):
    """Broker credentials persisted in PostgreSQL (one row per broker)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, broker: str) -> BrokerCredentials | None:
        record = await self._session.get(BrokerSettingsRecord, broker)
        return _to_entity(record) if record is not None else None

    async def upsert(self, credentials: BrokerCredentials) -> BrokerCredentials:
        record = await self._session.get(BrokerSettingsRecord, credentials.broker)
        if record is None:
            record = BrokerSettingsRecord(broker=credentials.broker)
            self._session.add(record)
        record.api_token = credentials.api_token
        record.account_id = credentials.account_id
        record.environment = credentials.environment
        await self._session.flush()
        await self._session.refresh(record)
        return _to_entity(record)

    async def delete(self, broker: str) -> None:
        await self._session.execute(
            sql_delete(BrokerSettingsRecord).where(BrokerSettingsRecord.broker == broker)
        )
