"""Tests for the auto-trader SQL repository, API routes and worker runner."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from quantlab.config import Settings
from quantlab.container import Container
from quantlab.domain.autotrader import AutoTrader
from quantlab.domain.market import Symbol, Timeframe
from quantlab.infrastructure.db.base import Base
from quantlab.infrastructure.db.repositories.autotrader import SqlAlchemyAutoTraderRepository
from quantlab.interfaces.api.app import create_app
from quantlab.interfaces.autotrader.runner import run

# -- SQL repository ----------------------------------------------------------------


@pytest.fixture
async def repo() -> AsyncIterator[SqlAlchemyAutoTraderRepository]:
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield SqlAlchemyAutoTraderRepository(session)
    await engine.dispose()


async def test_repository_crud_and_enabled_filter(repo: SqlAlchemyAutoTraderRepository) -> None:
    a = await repo.create(
        AutoTrader(
            strategy_id="atr_breakout",
            symbol=Symbol.XAUUSD,
            timeframe=Timeframe.H4,
            units=1.0,
            params={"breakout_atr": 1.7},
        )
    )
    await repo.create(
        AutoTrader(
            strategy_id="ema_cross", symbol=Symbol.EURUSD, timeframe=Timeframe.H1, units=1000.0
        )
    )
    assert len(await repo.list_all()) == 2
    assert await repo.list_enabled() == []  # both start disabled

    a.enabled = True
    a.last_action = "opened_long"
    await repo.update(a)
    enabled = await repo.list_enabled()
    assert len(enabled) == 1 and enabled[0].params == {"breakout_atr": 1.7}

    fetched = await repo.get(a.id)
    assert fetched is not None and fetched.last_action == "opened_long"
    await repo.delete(a.id)
    assert await repo.get(a.id) is None
    assert len(await repo.list_all()) == 1


# -- API routes --------------------------------------------------------------------


class FakeAutoTraderService:
    def __init__(self) -> None:
        self.store: dict[uuid.UUID, AutoTrader] = {}

    async def list_all(self) -> list[AutoTrader]:
        return list(self.store.values())

    async def create(self, strategy_id, symbol, timeframe, units, params=None, ml_model_id=None):  # type: ignore[no-untyped-def]
        from quantlab.strategies.registry import StrategyRegistry, UnknownStrategyError

        if strategy_id not in StrategyRegistry().discover().ids():
            raise UnknownStrategyError(strategy_id)
        at = AutoTrader(
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            units=units,
            params=params or {},
        )
        self.store[at.id] = at
        return at

    async def set_enabled(self, auto_trader_id: uuid.UUID, enabled: bool) -> AutoTrader | None:
        at = self.store.get(auto_trader_id)
        if at is None:
            return None
        at.enabled = enabled
        return at

    async def delete(self, auto_trader_id: uuid.UUID) -> bool:
        return self.store.pop(auto_trader_id, None) is not None


class AutoTraderStubContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.auto_trader_service = FakeAutoTraderService()

        class _Store:
            def coverage(self, *_a: object) -> object:
                return object()

        self.candle_store = _Store()


def client(app: FastAPI, container: AutoTraderStubContainer) -> httpx.AsyncClient:
    app.state.container = container
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_autotrader_routes_crud(settings: Settings) -> None:
    app = create_app(settings)
    container = AutoTraderStubContainer(settings)
    async with client(app, container) as c:
        created = await c.post(
            "/api/v1/autotraders",
            json={
                "strategy_id": "atr_breakout",
                "symbol": "XAUUSD",
                "timeframe": "H4",
                "units": 1,
                "params": {"breakout_atr": 1.73},
            },
        )
        assert created.status_code == 201
        at_id = created.json()["id"]
        assert created.json()["enabled"] is False

        listed = await c.get("/api/v1/autotraders")
        assert len(listed.json()) == 1

        toggled = await c.post(f"/api/v1/autotraders/{at_id}/toggle", json={"enabled": True})
        assert toggled.json()["enabled"] is True

        unknown = await c.post(
            "/api/v1/autotraders",
            json={"strategy_id": "nope", "symbol": "XAUUSD", "timeframe": "H4", "units": 1},
        )
        assert unknown.status_code == 404

        missing_toggle = await c.post(
            f"/api/v1/autotraders/{uuid.uuid4()}/toggle", json={"enabled": True}
        )
        assert missing_toggle.status_code == 404

        deleted = await c.delete(f"/api/v1/autotraders/{at_id}")
        assert deleted.status_code == 204
        assert (await c.delete(f"/api/v1/autotraders/{at_id}")).status_code == 404


# -- worker runner -----------------------------------------------------------------


async def test_runner_loops_and_calls_run_tick() -> None:
    ticks: list[object] = []

    class FakeService:
        async def run_tick(self, now: object) -> list[object]:
            ticks.append(now)
            return []

    class FakeContainer:
        auto_trader_service = FakeService()

    await run(FakeContainer(), poll_seconds=0, iterations=3)  # type: ignore[arg-type]
    assert len(ticks) == 3


async def test_runner_survives_a_failing_tick() -> None:
    calls = {"n": 0}

    class FakeService:
        async def run_tick(self, now: object) -> list[object]:
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("boom")
            return []

    class FakeContainer:
        auto_trader_service = FakeService()

    await run(FakeContainer(), poll_seconds=0, iterations=2)  # type: ignore[arg-type]
    assert calls["n"] == 2  # kept going after the failure


def test_container_exposes_auto_trader_service() -> None:
    container = Container(Settings(_env_file=None, environment="test", auth_enabled=False))
    assert container.auto_trader_service is container.auto_trader_service
