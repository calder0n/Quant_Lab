"""Authentication and user administration."""

import logging
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from quantlab.application.ports import AuthRepository
from quantlab.domain.auth import ApiKey, AuthError, Role, User
from quantlab.infrastructure.security import (
    create_access_token,
    decode_access_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)

AuthRepositoryFactory = Callable[[], AbstractAsyncContextManager[AuthRepository]]


class AuthService:
    """Login, session tokens, API keys and user management."""

    def __init__(
        self, repositories: AuthRepositoryFactory, secret_key: str, token_ttl_minutes: int
    ) -> None:
        self._repositories = repositories
        self._secret = secret_key
        self._ttl = token_ttl_minutes

    async def is_initialized(self) -> bool:
        async with self._repositories() as repo:
            return await repo.count_users() > 0

    async def setup_first_admin(self, username: str, password: str) -> User:
        """Create the first (admin) user; only allowed while no users exist."""
        async with self._repositories() as repo:
            if await repo.count_users() > 0:
                raise AuthError("Setup already completed")
            user = User(username=username, role=Role.ADMIN, password_hash=hash_password(password))
            created = await repo.add_user(user)
        logger.info("First admin user created: %s", username)
        return created

    async def login(self, username: str, password: str) -> tuple[str, User]:
        async with self._repositories() as repo:
            user = await repo.get_user(username)
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Invalid username or password")
        token = create_access_token(user.username, user.role, self._secret, self._ttl)
        return token, user

    async def authenticate_token(self, token: str) -> User:
        username, _role = decode_access_token(token, self._secret)
        async with self._repositories() as repo:
            user = await repo.get_user(username)
        if user is None:
            raise AuthError("Unknown user")
        return user

    async def authenticate_api_key(self, key: str) -> User:
        async with self._repositories() as repo:
            found = await repo.find_api_key(hash_api_key(key))
        if found is None:
            raise AuthError("Invalid API key")
        _api_key, user = found
        return user

    async def create_user(self, username: str, password: str, role: Role) -> User:
        async with self._repositories() as repo:
            if await repo.get_user(username) is not None:
                raise AuthError(f"User {username!r} already exists")
            return await repo.add_user(
                User(username=username, role=role, password_hash=hash_password(password))
            )

    async def list_users(self) -> list[User]:
        async with self._repositories() as repo:
            return await repo.list_users()

    async def create_api_key(self, user: User, name: str) -> tuple[str, ApiKey]:
        """Generate a key for ``user``; the plaintext is returned exactly once."""
        plaintext = generate_api_key()
        api_key = ApiKey(
            user_id=user.id, name=name, prefix=plaintext[:7], key_hash=hash_api_key(plaintext)
        )
        async with self._repositories() as repo:
            created = await repo.add_api_key(api_key)
        return plaintext, created

    async def list_api_keys(self, user: User) -> list[ApiKey]:
        async with self._repositories() as repo:
            return await repo.list_api_keys(user.id)
