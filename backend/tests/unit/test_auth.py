"""Tests for the auth service, repository and API routes."""

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from quantlab.application.ports import AuthRepository
from quantlab.application.services.auth import AuthService
from quantlab.config import Settings
from quantlab.domain.auth import ApiKey, AuthError, Role, User
from quantlab.infrastructure.db.base import Base
from quantlab.infrastructure.db.repositories.auth import SqlAlchemyAuthRepository
from quantlab.interfaces.api.app import create_app


class InMemoryAuthRepo(AuthRepository):
    def __init__(self, users: dict[str, User], keys: list[ApiKey]) -> None:
        self._users = users
        self._keys = keys

    async def count_users(self) -> int:
        return len(self._users)

    async def get_user(self, username: str) -> User | None:
        return self._users.get(username)

    async def add_user(self, user: User) -> User:
        self._users[user.username] = user
        return user

    async def list_users(self) -> list[User]:
        return list(self._users.values())

    async def add_api_key(self, api_key: ApiKey) -> ApiKey:
        self._keys.append(api_key)
        return api_key

    async def find_api_key(self, key_hash: str) -> tuple[ApiKey, User] | None:
        for key in self._keys:
            if key.key_hash == key_hash:
                user = next(u for u in self._users.values() if u.id == key.user_id)
                return key, user
        return None

    async def list_api_keys(self, user_id: uuid.UUID) -> list[ApiKey]:
        return [key for key in self._keys if key.user_id == user_id]


def make_service() -> tuple[AuthService, dict[str, User]]:
    users: dict[str, User] = {}
    keys: list[ApiKey] = []

    @asynccontextmanager
    async def repositories() -> AsyncIterator[AuthRepository]:
        yield InMemoryAuthRepo(users, keys)

    return AuthService(repositories, secret_key="test-secret", token_ttl_minutes=5), users


# -- service ---------------------------------------------------------------------


async def test_setup_creates_first_admin_exactly_once() -> None:
    service, _ = make_service()
    assert not await service.is_initialized()
    user = await service.setup_first_admin("admin", "password123")
    assert user.role == Role.ADMIN
    assert await service.is_initialized()
    with pytest.raises(AuthError, match="already completed"):
        await service.setup_first_admin("other", "password123")


async def test_login_and_token_round_trip() -> None:
    service, _ = make_service()
    await service.setup_first_admin("admin", "password123")
    token, _ = await service.login("admin", "password123")
    assert (await service.authenticate_token(token)).username == "admin"
    with pytest.raises(AuthError):
        await service.login("admin", "wrong-password")
    with pytest.raises(AuthError):
        await service.login("ghost", "password123")


async def test_api_key_lifecycle() -> None:
    service, _ = make_service()
    admin = await service.setup_first_admin("admin", "password123")
    plaintext, key = await service.create_api_key(admin, "ci")
    assert plaintext.startswith("ql_")
    assert key.prefix == plaintext[:7]
    assert (await service.authenticate_api_key(plaintext)).username == "admin"
    with pytest.raises(AuthError):
        await service.authenticate_api_key("ql_invalid")
    assert len(await service.list_api_keys(admin)) == 1


async def test_create_user_rejects_duplicates() -> None:
    service, _ = make_service()
    await service.setup_first_admin("admin", "password123")
    await service.create_user("viewer1", "password123", Role.VIEWER)
    with pytest.raises(AuthError, match="already exists"):
        await service.create_user("viewer1", "password123", Role.VIEWER)


# -- SQL repository ----------------------------------------------------------------


async def test_sql_auth_repository_round_trip() -> None:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        repo = SqlAlchemyAuthRepository(session)
        assert await repo.count_users() == 0
        user = await repo.add_user(User(username="admin", role=Role.ADMIN, password_hash="h"))
        assert await repo.count_users() == 1
        fetched = await repo.get_user("admin")
        assert fetched is not None and fetched.role == Role.ADMIN
        key = await repo.add_api_key(
            ApiKey(user_id=user.id, name="ci", prefix="ql_abcd", key_hash="hash1")
        )
        found = await repo.find_api_key("hash1")
        assert found is not None and found[0].id == key.id and found[1].username == "admin"
        assert await repo.find_api_key("nope") is None
        assert len(await repo.list_api_keys(user.id)) == 1
        assert len(await repo.list_users()) == 1
    await engine.dispose()


# -- routes with auth enabled --------------------------------------------------------


class AuthStubContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.users: dict[str, User] = {}
        self.keys: list[ApiKey] = []

        @asynccontextmanager
        async def repositories() -> AsyncIterator[AuthRepository]:
            yield InMemoryAuthRepo(self.users, self.keys)

        self.auth_service = AuthService(
            repositories, secret_key=settings.secret_key, token_ttl_minutes=5
        )
        from quantlab.strategies.registry import StrategyRegistry

        self.strategy_registry = StrategyRegistry().discover()


def build_client(app: FastAPI, container: AuthStubContainer) -> httpx.AsyncClient:
    app.state.container = container
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        _env_file=None, environment="test", auth_enabled=True, secret_key="route-secret"
    )


async def test_full_auth_flow_via_routes(auth_settings: Settings) -> None:
    app = create_app(auth_settings)
    container = AuthStubContainer(auth_settings)
    async with build_client(app, container) as client:
        status_before = (await client.get("/api/v1/auth/status")).json()
        assert status_before == {"auth_enabled": True, "initialized": False}

        # protected routes reject anonymous requests
        anonymous = await client.get("/api/v1/strategies")
        assert anonymous.status_code == 401

        setup = await client.post(
            "/api/v1/auth/setup", json={"username": "admin", "password": "password123"}
        )
        assert setup.status_code == 201
        token = setup.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        again = await client.post(
            "/api/v1/auth/setup", json={"username": "someone-else", "password": "password123"}
        )
        assert again.status_code == 409

        me = await client.get("/api/v1/auth/me", headers=headers)
        assert me.json()["role"] == "admin"

        authorized = await client.get("/api/v1/strategies", headers=headers)
        assert authorized.status_code == 200

        bad_login = await client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"}
        )
        assert bad_login.status_code == 401


async def test_viewer_cannot_mutate(auth_settings: Settings) -> None:
    app = create_app(auth_settings)
    container = AuthStubContainer(auth_settings)
    async with build_client(app, container) as client:
        setup = await client.post(
            "/api/v1/auth/setup", json={"username": "admin", "password": "password123"}
        )
        admin_headers = {"Authorization": f"Bearer {setup.json()['access_token']}"}
        created = await client.post(
            "/api/v1/auth/users",
            json={"username": "viewer1", "password": "password123", "role": "viewer"},
            headers=admin_headers,
        )
        assert created.status_code == 201
        login = await client.post(
            "/api/v1/auth/login", json={"username": "viewer1", "password": "password123"}
        )
        viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        read = await client.get("/api/v1/strategies", headers=viewer_headers)
        assert read.status_code == 200
        write = await client.post("/api/v1/datasets/sync", json={}, headers=viewer_headers)
        assert write.status_code == 403
        users = await client.get("/api/v1/auth/users", headers=viewer_headers)
        assert users.status_code == 403


async def test_api_key_authenticates_requests(auth_settings: Settings) -> None:
    app = create_app(auth_settings)
    container = AuthStubContainer(auth_settings)
    async with build_client(app, container) as client:
        setup = await client.post(
            "/api/v1/auth/setup", json={"username": "admin", "password": "password123"}
        )
        headers = {"Authorization": f"Bearer {setup.json()['access_token']}"}
        created = await client.post("/api/v1/auth/api-keys", json={"name": "ci"}, headers=headers)
        assert created.status_code == 201
        api_key = created.json()["api_key"]

        listed = await client.get("/api/v1/auth/api-keys", headers=headers)
        assert "api_key" not in listed.json()[0]  # plaintext never shown again

        via_key = await client.get("/api/v1/strategies", headers={"X-API-Key": api_key})
        assert via_key.status_code == 200
        bad_key = await client.get("/api/v1/strategies", headers={"X-API-Key": "ql_wrong"})
        assert bad_key.status_code == 401
