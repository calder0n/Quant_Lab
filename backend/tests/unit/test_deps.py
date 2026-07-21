"""Tests for FastAPI dependency helpers."""

from typing import cast

from quantlab.config import Settings
from quantlab.container import Container
from quantlab.interfaces.api.deps import get_session
from tests.conftest import StubContainer, StubSession


async def test_get_session_yields_and_closes_a_session(settings: Settings) -> None:
    stub = StubContainer(settings)
    sessions = [session async for session in get_session(cast(Container, stub))]
    assert len(sessions) == 1
    assert isinstance(sessions[0], StubSession)
