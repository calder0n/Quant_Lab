"""Trading endpoints: account status, kill switch and one-shot execution.

Every mutation requires the admin role. Enabling trading against a live
environment additionally requires the typed confirmation ``TRADE-LIVE``.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from quantlab.application.services.trading import ExecutionReport, TradingStatus
from quantlab.domain.market import Symbol, Timeframe
from quantlab.domain.trading import (
    AccountSummary,
    LiveConfirmationError,
    OrderResult,
    Position,
    TradeRecord,
    TradingDisabledError,
)
from quantlab.interfaces.api.deps import AdminUser, ContainerDep, CurrentUser
from quantlab.strategies.base import InvalidParameterError, ParamValue
from quantlab.strategies.registry import UnknownStrategyError

router = APIRouter(prefix="/trading", tags=["trading"])


class AccountOut(BaseModel):
    account_id: str
    currency: str
    balance: float
    nav: float
    margin_used: float
    margin_available: float
    open_position_count: int

    @classmethod
    def from_entity(cls, account: AccountSummary) -> "AccountOut":
        return cls(**account.__dict__)


class PositionOut(BaseModel):
    symbol: str
    units: float
    average_price: float
    unrealized_pl: float

    @classmethod
    def from_entity(cls, position: Position) -> "PositionOut":
        return cls(**position.__dict__)


class TradingStatusOut(BaseModel):
    enabled: bool
    environment: str
    updated_at: datetime | None
    account: AccountOut | None
    positions: list[PositionOut]
    detail: str | None

    @classmethod
    def from_entity(cls, trading_status: TradingStatus) -> "TradingStatusOut":
        return cls(
            enabled=trading_status.state.enabled,
            environment=trading_status.environment,
            updated_at=trading_status.state.updated_at,
            account=(
                AccountOut.from_entity(trading_status.account) if trading_status.account else None
            ),
            positions=[PositionOut.from_entity(p) for p in trading_status.positions],
            detail=trading_status.detail,
        )


class ToggleIn(BaseModel):
    enabled: bool
    confirm: str | None = None


class ExecuteIn(BaseModel):
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    units: float = Field(gt=0, le=1_000_000)
    params: dict[str, ParamValue] | None = None
    ml_model_id: str | None = None


class OrderOut(BaseModel):
    instrument: str
    units: float
    filled: bool
    order_id: str
    detail: str

    @classmethod
    def from_entity(cls, order: OrderResult) -> "OrderOut":
        return cls(**order.__dict__)


class ExecutionOut(BaseModel):
    action: str
    symbol: Symbol
    signal_time: str
    orders: list[OrderOut]

    @classmethod
    def from_entity(cls, report: ExecutionReport) -> "ExecutionOut":
        return cls(
            action=report.action,
            symbol=report.symbol,
            signal_time=report.signal_time,
            orders=[OrderOut.from_entity(order) for order in report.orders],
        )


class TradeRecordOut(BaseModel):
    id: str
    executed_at: datetime | None
    strategy_id: str
    symbol: Symbol
    timeframe: str
    action: str
    source: str
    units: float
    entry_price: float | None
    exit_price: float | None
    sl_price: float | None
    tp_price: float | None
    trailing_distance: float | None
    realized_pl: float | None
    order_id: str
    filled: bool
    detail: str | None
    signal_time: str | None
    broker_trade_id: str | None
    params: dict[str, ParamValue]

    @classmethod
    def from_entity(cls, record: TradeRecord) -> "TradeRecordOut":
        return cls(
            id=str(record.id),
            executed_at=record.executed_at,
            strategy_id=record.strategy_id,
            symbol=record.symbol,
            timeframe=record.timeframe,
            action=record.action,
            source=record.source,
            units=record.units,
            entry_price=record.entry_price,
            exit_price=record.exit_price,
            sl_price=record.sl_price,
            tp_price=record.tp_price,
            trailing_distance=record.trailing_distance,
            realized_pl=record.realized_pl,
            order_id=record.order_id,
            filled=record.filled,
            detail=record.detail,
            signal_time=record.signal_time,
            broker_trade_id=record.broker_trade_id,
            params=record.params,
        )


@router.get("/pnl-daily", response_model=dict[str, float])
async def pnl_daily(_: CurrentUser, container: ContainerDep) -> dict[str, float]:
    """Realized P/L per UTC day (``YYYY-MM-DD`` → total) for the P&L calendar."""
    return await container.trading_service.pnl_by_day()


@router.get("/history", response_model=list[TradeRecordOut])
async def trade_history(
    _: CurrentUser,
    container: ContainerDep,
    limit: int = Query(100, ge=1, le=500),
    strategy_id: str | None = Query(None),
) -> list[TradeRecordOut]:
    """Locally recorded executions, newest first, with reconciled broker exits."""
    await container.trading_service.reconcile_broker_closes()
    records = await container.trading_service.history(limit=limit, strategy_id=strategy_id)
    return [TradeRecordOut.from_entity(record) for record in records]


@router.get("/status", response_model=TradingStatusOut)
async def trading_status(_: CurrentUser, container: ContainerDep) -> TradingStatusOut:
    """Kill-switch state, account summary and open positions."""
    return TradingStatusOut.from_entity(await container.trading_service.status())


@router.post("/toggle", response_model=TradingStatusOut)
async def toggle_trading(body: ToggleIn, _: AdminUser, container: ContainerDep) -> TradingStatusOut:
    """Flip the kill switch. Live environments require confirm='TRADE-LIVE'."""
    try:
        await container.trading_service.set_enabled(body.enabled, body.confirm)
    except LiveConfirmationError as exc:
        raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, detail=str(exc)) from exc
    return TradingStatusOut.from_entity(await container.trading_service.status())


@router.post("/execute", response_model=ExecutionOut)
async def execute(body: ExecuteIn, _: AdminUser, container: ContainerDep) -> ExecutionOut:
    """Evaluate a strategy on fresh broker candles and act on the latest signal."""
    try:
        report = await container.trading_service.execute(
            strategy_id=body.strategy_id,
            symbol=body.symbol,
            timeframe=body.timeframe,
            units=body.units,
            params=body.params,
            ml_model_id=body.ml_model_id,
        )
    except TradingDisabledError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except UnknownStrategyError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=f"Unknown strategy: {exc.args[0]}"
        ) from exc
    except InvalidParameterError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return ExecutionOut.from_entity(report)
