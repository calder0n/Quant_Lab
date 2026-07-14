"""Tests for the strategies and backtests API routes."""

from datetime import datetime

import httpx
import pandas as pd
from fastapi import FastAPI

from quantlab.application.services.backtesting import DataNotAvailableError
from quantlab.config import Settings
from quantlab.domain.backtest import BacktestMetrics, BacktestResult, CostModel
from quantlab.domain.market import Symbol, Timeframe
from quantlab.interfaces.api.app import create_app
from quantlab.strategies.base import InvalidParameterError, ParamValue
from quantlab.strategies.registry import StrategyRegistry, UnknownStrategyError
from tests.factories import utc


class FakeBacktestService:
    def run(
        self,
        strategy_id: str,
        symbol: Symbol,
        timeframe: Timeframe,
        params: dict[str, ParamValue] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        costs: CostModel | None = None,
    ) -> BacktestResult:
        if strategy_id == "nope":
            raise UnknownStrategyError("nope")
        if symbol == Symbol.US30:
            raise DataNotAvailableError("No local data for US30 H1")
        if params and "bad" in params:
            raise InvalidParameterError("Unknown parameters: ['bad']")
        return BacktestResult(
            metrics=BacktestMetrics(sharpe=1.2, trades=42, total_return=0.3),
            equity=pd.Series(
                [10_000.0, 10_500.0, 13_000.0],
                index=pd.DatetimeIndex([utc(2024, 1, 1, h) for h in range(3)], tz="UTC"),
            ),
            fitness=0.55,
            params={"fast_period": 12},
        )


class RoutesStubContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.strategy_registry = StrategyRegistry().discover()
        self.backtest_service = FakeBacktestService()


def build_client(app: FastAPI, container: RoutesStubContainer) -> httpx.AsyncClient:
    app.state.container = container
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_list_strategies_exposes_all_plugins(settings: Settings) -> None:
    app = create_app(settings)
    async with build_client(app, RoutesStubContainer(settings)) as client:
        response = await client.get("/api/v1/strategies")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 15
    ema = next(s for s in body if s["strategy_id"] == "ema_cross")
    assert ema["name"] == "EMA Cross"
    param_names = {p["name"] for p in ema["parameters"]}
    assert {"fast_period", "slow_period", "sl_atr", "tp_atr"} <= param_names


async def test_run_backtest_returns_metrics_and_equity(settings: Settings) -> None:
    app = create_app(settings)
    async with build_client(app, RoutesStubContainer(settings)) as client:
        response = await client.post(
            "/api/v1/backtests",
            json={"strategy_id": "ema_cross", "symbol": "EURUSD", "timeframe": "H1"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["fitness"] == 0.55
    assert body["metrics"]["trades"] == 42
    assert len(body["equity"]) == 3
    assert body["params"] == {"fast_period": 12}


async def test_unknown_strategy_maps_to_404(settings: Settings) -> None:
    app = create_app(settings)
    async with build_client(app, RoutesStubContainer(settings)) as client:
        response = await client.post(
            "/api/v1/backtests",
            json={"strategy_id": "nope", "symbol": "EURUSD", "timeframe": "H1"},
        )
    assert response.status_code == 404
    assert "Unknown strategy" in response.json()["detail"]


async def test_missing_data_maps_to_404(settings: Settings) -> None:
    app = create_app(settings)
    async with build_client(app, RoutesStubContainer(settings)) as client:
        response = await client.post(
            "/api/v1/backtests",
            json={"strategy_id": "ema_cross", "symbol": "US30", "timeframe": "H1"},
        )
    assert response.status_code == 404
    assert "No local data" in response.json()["detail"]


async def test_invalid_params_map_to_422(settings: Settings) -> None:
    app = create_app(settings)
    async with build_client(app, RoutesStubContainer(settings)) as client:
        response = await client.post(
            "/api/v1/backtests",
            json={
                "strategy_id": "ema_cross",
                "symbol": "EURUSD",
                "timeframe": "H1",
                "params": {"bad": 1},
            },
        )
    assert response.status_code == 422
