"""SQLAlchemy implementation of the ``BrokerSettingsRepository`` port.

The API token is encrypted at rest (Fernet derived from ``QL_SECRET_KEY``).
Legacy plaintext rows remain readable and are re-encrypted on the next save.
"""

from typing import cast

from cryptography.fernet import Fernet
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from quantlab.application.ports import BrokerSettingsRepository
from quantlab.domain.broker import BrokerCredentials, BrokerEnvironment
from quantlab.infrastructure.db.models.broker_settings import BrokerSettingsRecord
from quantlab.infrastructure.security import decrypt_secret, encrypt_secret


class SqlAlchemyBrokerSettingsRepository(BrokerSettingsRepository):
    """Broker credentials persisted in PostgreSQL (one row per broker)."""

    def __init__(self, session: AsyncSession, fernet: Fernet | None = None) -> None:
        self._session = session
        self._fernet = fernet

    def _to_entity(self, record: BrokerSettingsRecord) -> BrokerCredentials:
        token = record.api_token
        if self._fernet is not None:
            token = decrypt_secret(token, self._fernet)
        return BrokerCredentials(
            broker=record.broker,
            api_token=token,
            account_id=record.account_id,
            environment=cast(BrokerEnvironment, record.environment),
            updated_at=record.updated_at,
        )

    async def get(self, broker: str) -> BrokerCredentials | None:
        record = await self._session.get(BrokerSettingsRecord, broker)
        return self._to_entity(record) if record is not None else None

    async def upsert(self, credentials: BrokerCredentials) -> BrokerCredentials:
        record = await self._session.get(BrokerSettingsRecord, credentials.broker)
        if record is None:
            record = BrokerSettingsRecord(broker=credentials.broker)
            self._session.add(record)
        record.api_token = (
            encrypt_secret(credentials.api_token, self._fernet)
            if self._fernet is not None
            else credentials.api_token
        )
        record.account_id = credentials.account_id
        record.environment = credentials.environment
        await self._session.flush()
        await self._session.refresh(record)
        return self._to_entity(record)

    async def delete(self, broker: str) -> None:
        await self._session.execute(
            sql_delete(BrokerSettingsRecord).where(BrokerSettingsRecord.broker == broker)
        )
