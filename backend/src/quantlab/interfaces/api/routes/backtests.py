"""Backtest execution endpoint."""

from datetime import datetime
from typing import cast

import pandas as pd
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from quantlab.application.services.backtesting import DataNotAvailableError
from quantlab.domain.backtest import BacktestMetrics, BacktestResult, CostModel
from quantlab.domain.market import Symbol, Timeframe
from quantlab.interfaces.api.deps import ContainerDep
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


class EquityPoint(BaseModel):
    time: datetime
    value: float


class BacktestResponse(BaseModel):
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    params: dict[str, ParamValue]
    fitness: float
    metrics: BacktestMetrics
    equity: list[EquityPoint]

    @classmethod
    def from_result(cls, request: BacktestRequest, result: BacktestResult) -> "BacktestResponse":
        index = cast(pd.DatetimeIndex, result.equity.index)
        equity = [
            EquityPoint(time=moment, value=float(value))
            for moment, value in zip(index.to_pydatetime(), result.equity.to_numpy(), strict=True)
        ]
        return cls(
            strategy_id=request.strategy_id,
            symbol=request.symbol,
            timeframe=request.timeframe,
            params=result.params,
            fitness=result.fitness,
            metrics=result.metrics,
            equity=equity,
        )


@router.post("", response_model=BacktestResponse)
def run_backtest(request: BacktestRequest, container: ContainerDep) -> BacktestResponse:
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
