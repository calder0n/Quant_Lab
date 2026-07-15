"""Shared fixtures and lightweight stubs for backing services."""

from types import TracebackType
from typing import Self

import pytest

from quantlab.config import Settings


class StubSession:
    """Async-context-manager stand-in for an SQLAlchemy session."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error
        self.executed: list[str] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def execute(self, statement: object) -> None:
        if self._error is not None:
            raise self._error
        self.executed.append(str(statement))


class StubRedis:
    """Stand-in for the async Redis client."""

    def __init__(self, error: Exception | None = None) -> None:
        self._error = error

    async def ping(self) -> bool:
        if self._error is not None:
            raise self._error
        return True


class StubContainer:
    """Minimal container surface used by the API layer."""

    def __init__(
        self,
        settings: Settings,
        db_error: Exception | None = None,
        redis_error: Exception | None = None,
    ) -> None:
        self.settings = settings
        self._db_error = db_error
        self.redis = StubRedis(error=redis_error)
        self.sessions: list[StubSession] = []

    def session_factory(self) -> StubSession:
        session = StubSession(error=self._db_error)
        self.sessions.append(session)
        return session


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, environment="test", auth_enabled=False)
