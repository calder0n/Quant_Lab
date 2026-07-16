"""Automated-trading assignment endpoints.

An assignment pairs a strategy (with tuned parameters) to a symbol/timeframe and
size. The dedicated auto-trader worker runs enabled assignments on each bar,
provided the global kill switch is also on. Mutations require the admin role.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from quantlab.domain.autotrader import AutoTrader
from quantlab.domain.market import Symbol, Timeframe
from quantlab.interfaces.api.deps import AdminUser, ContainerDep, CurrentUser
from quantlab.strategies.base import InvalidParameterError, ParamValue
from quantlab.strategies.registry import UnknownStrategyError

router = APIRouter(prefix="/autotraders", tags=["autotraders"])


class AutoTraderCreate(BaseModel):
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    units: float = Field(gt=0, le=1_000_000)
    params: dict[str, ParamValue] = Field(default_factory=dict)


class ToggleIn(BaseModel):
    enabled: bool


class AutoTraderOut(BaseModel):
    id: uuid.UUID
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    units: float
    params: dict[str, ParamValue]
    enabled: bool
    last_run: datetime | None
    last_signal_time: str | None
    last_action: str | None
    message: str | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_entity(cls, at: AutoTrader) -> "AutoTraderOut":
        return cls(
            id=at.id,
            strategy_id=at.strategy_id,
            symbol=at.symbol,
            timeframe=at.timeframe,
            units=at.units,
            params=at.params,
            enabled=at.enabled,
            last_run=at.last_run,
            last_signal_time=at.last_signal_time,
            last_action=at.last_action,
            message=at.message,
            created_at=at.created_at,
            updated_at=at.updated_at,
        )


@router.get("", response_model=list[AutoTraderOut])
async def list_autotraders(_: CurrentUser, container: ContainerDep) -> list[AutoTraderOut]:
    """Every auto-trading assignment, newest first."""
    return [AutoTraderOut.from_entity(at) for at in await container.auto_trader_service.list_all()]


@router.post("", response_model=AutoTraderOut, status_code=status.HTTP_201_CREATED)
async def create_autotrader(
    body: AutoTraderCreate, _: AdminUser, container: ContainerDep
) -> AutoTraderOut:
    """Register a strategy to auto-trade a symbol/timeframe (starts disabled)."""
    if container.candle_store.coverage(body.symbol, body.timeframe) is None:
        # Not fatal for trading (uses live OANDA data) but usually a mistake.
        pass
    try:
        at = await container.auto_trader_service.create(
            strategy_id=body.strategy_id,
            symbol=body.symbol,
            timeframe=body.timeframe,
            units=body.units,
            params=body.params,
        )
    except UnknownStrategyError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Unknown strategy: {body.strategy_id}"
        ) from exc
    except InvalidParameterError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return AutoTraderOut.from_entity(at)


@router.post("/{auto_trader_id}/toggle", response_model=AutoTraderOut)
async def toggle_autotrader(
    auto_trader_id: uuid.UUID, body: ToggleIn, _: AdminUser, container: ContainerDep
) -> AutoTraderOut:
    """Enable or disable one assignment (global kill switch still applies)."""
    at = await container.auto_trader_service.set_enabled(auto_trader_id, body.enabled)
    if at is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Auto-trader not found")
    return AutoTraderOut.from_entity(at)


@router.delete("/{auto_trader_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_autotrader(
    auto_trader_id: uuid.UUID, _: AdminUser, container: ContainerDep
) -> None:
    if not await container.auto_trader_service.delete(auto_trader_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Auto-trader not found")
