"""SQLAlchemy implementations of the auth and trading-state ports."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from quantlab.application.ports import AuthRepository, TradingStateRepository
from quantlab.domain.auth import ApiKey, Role, User
from quantlab.domain.trading import TradingState
from quantlab.infrastructure.db.models.auth import ApiKeyRecord, TradingStateRecord, UserRecord


def _user_to_entity(record: UserRecord) -> User:
    return User(
        id=record.id,
        username=record.username,
        role=Role(record.role),
        password_hash=record.password_hash,
        created_at=record.created_at,
    )


def _key_to_entity(record: ApiKeyRecord) -> ApiKey:
    return ApiKey(
        id=record.id,
        user_id=record.user_id,
        name=record.name,
        prefix=record.prefix,
        key_hash=record.key_hash,
        created_at=record.created_at,
    )


class SqlAlchemyAuthRepository(AuthRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_users(self) -> int:
        result = await self._session.execute(select(func.count(UserRecord.id)))
        return int(result.scalar_one())

    async def get_user(self, username: str) -> User | None:
        result = await self._session.execute(
            select(UserRecord).where(UserRecord.username == username)
        )
        record = result.scalar_one_or_none()
        return _user_to_entity(record) if record is not None else None

    async def add_user(self, user: User) -> User:
        record = UserRecord(
            id=user.id,
            username=user.username,
            password_hash=user.password_hash,
            role=user.role.value,
        )
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return _user_to_entity(record)

    async def list_users(self) -> list[User]:
        result = await self._session.execute(select(UserRecord).order_by(UserRecord.username))
        return [_user_to_entity(record) for record in result.scalars()]

    async def add_api_key(self, api_key: ApiKey) -> ApiKey:
        record = ApiKeyRecord(
            id=api_key.id,
            user_id=api_key.user_id,
            name=api_key.name,
            prefix=api_key.prefix,
            key_hash=api_key.key_hash,
        )
        self._session.add(record)
        await self._session.flush()
        await self._session.refresh(record)
        return _key_to_entity(record)

    async def find_api_key(self, key_hash: str) -> tuple[ApiKey, User] | None:
        result = await self._session.execute(
            select(ApiKeyRecord, UserRecord)
            .join(UserRecord, ApiKeyRecord.user_id == UserRecord.id)
            .where(ApiKeyRecord.key_hash == key_hash)
        )
        row = result.first()
        if row is None:
            return None
        key_record, user_record = row
        return _key_to_entity(key_record), _user_to_entity(user_record)

    async def list_api_keys(self, user_id: uuid.UUID) -> list[ApiKey]:
        result = await self._session.execute(
            select(ApiKeyRecord).where(ApiKeyRecord.user_id == user_id)
        )
        return [_key_to_entity(record) for record in result.scalars()]


class SqlAlchemyTradingStateRepository(TradingStateRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> TradingState:
        record = await self._session.get(TradingStateRecord, 1)
        if record is None:
            return TradingState(enabled=False)
        return TradingState(enabled=record.enabled, updated_at=record.updated_at)

    async def set_enabled(self, enabled: bool) -> TradingState:
        record = await self._session.get(TradingStateRecord, 1)
        if record is None:
            record = TradingStateRecord(id=1, enabled=enabled)
            self._session.add(record)
        else:
            record.enabled = enabled
        await self._session.flush()
        await self._session.refresh(record)
        return TradingState(enabled=record.enabled, updated_at=record.updated_at)
