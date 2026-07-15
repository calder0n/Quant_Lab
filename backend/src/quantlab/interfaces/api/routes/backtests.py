"""Backtest execution endpoint."""

from datetime import datetime
from typing import cast

import pandas as pd
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from quantlab.application.services.backtesting import DataNotAvailableError
from quantlab.domain.backtest import BacktestMetrics, BacktestResult, CostModel
from quantlab.domain.market import Symbol, Timeframe
from quantlab.interfaces.api.deps import AdminUser, ContainerDep
from quantlab.strategies.base import InvalidParameterError, ParamValue
from quantlab.strategies.registry import UnknownStrategyError

router = APIRouter(prefix="/backtests", tags=["backtests"])


class BacktestRequest(BaseModel):
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    params: dict[str, ParamValue] = Field(default_factory=dict)
    start: datetime | None = None
    end: datetime | None = None
    commission_pct: float = Field(0.0, ge=0.0, le=0.01)
    slippage_pct: float = Field(0.0, ge=0.0, le=0.01)
    use_spread: bool = True
    chart_bars: int = Field(400, ge=0, le=3000)


class EquityPoint(BaseModel):
    time: datetime
    value: float


class MarkerOut(BaseModel):
    time: str
    price: float


class ChartOut(BaseModel):
    time: list[str]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    overlays: dict[str, list[float | None]]
    markers: dict[str, list[MarkerOut]]


class BacktestResponse(BaseModel):
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    params: dict[str, ParamValue]
    fitness: float
    metrics: BacktestMetrics
    equity: list[EquityPoint]
    trade_returns: list[float]
    chart: ChartOut | None = None

    @classmethod
    def from_result(cls, request: BacktestRequest, result: BacktestResult) -> "BacktestResponse":
        index = cast(pd.DatetimeIndex, result.equity.index)
        equity = [
            EquityPoint(time=moment, value=float(value))
            for moment, value in zip(index.to_pydatetime(), result.equity.to_numpy(), strict=True)
        ]
        chart = None
        if result.chart is not None:
            chart = ChartOut(
                time=result.chart.time,
                open=result.chart.open,
                high=result.chart.high,
                low=result.chart.low,
                close=result.chart.close,
                overlays=result.chart.overlays,
                markers={
                    name: [MarkerOut(time=m.time, price=m.price) for m in points]
                    for name, points in result.chart.markers.items()
                },
            )
        return cls(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            timeframe=request.timeframe,
            params=result.params,
            fitness=result.fitness,
            metrics=result.metrics,
            equity=equity,
            trade_returns=result.trade_returns,
            chart=chart,
        )


@router.post("", response_model=BacktestResponse)
def run_backtest(
    request: BacktestRequest, container: ContainerDep, _: AdminUser
) -> BacktestResponse:
    """Run one strategy over locally stored data (sync the dataset first)."""
    try:
        result = container.backtest_service.run(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            timeframe=request.timeframe,
            params=request.params,
            start=request.start,
            end=request.end,
            costs=CostModel(
                commission_pct=request.commission_pct,
                slippage_pct=request.slippage_pct,
                use_spread=request.use_spread,
            ),
            chart_bars=request.chart_bars,
        )
    except UnknownStrategyError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Unknown strategy: {exc.args[0]}"
        ) from exc
    except DataNotAvailableError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except InvalidParameterError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return BacktestResponse.from_result(request, result)
