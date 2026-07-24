"""Live/paper trading concepts.

Trading is OFF by default and persists as an explicit switch. Enabling it
against a live-money environment requires a typed confirmation; the platform
never enables itself.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from quantlab.domain.events import DomainEvent
from quantlab.domain.market import Symbol

LIVE_CONFIRMATION = "TRADE-LIVE"


@dataclass(frozen=True)
class AccountSummary:
    account_id: str
    currency: str
    balance: float
    nav: float
    margin_used: float
    margin_available: float
    open_position_count: int


@dataclass(frozen=True)
class Position:
    symbol: str
    units: float  # negative = short
    average_price: float
    unrealized_pl: float


@dataclass(frozen=True)
class OrderResult:
    instrument: str
    units: float
    filled: bool
    order_id: str
    detail: str = ""
    price: float | None = None  # broker fill price, when the order filled
    realized_pl: float | None = None  # realized P/L reported by the broker (closes)
    trade_id: str | None = None  # broker trade id opened by this order (for reconciliation)


@dataclass(frozen=True)
class BrokerClose:
    """A position the broker closed on its own (take-profit / stop / trailing).

    These fills happen server-side and never pass through the platform's close
    path, so they're pulled from the broker's transaction feed and reconciled
    into the history via ``trade_id`` (matching the open the platform recorded).
    """

    trade_id: str  # the broker trade id that was closed
    transaction_id: str  # the closing fill's id (dedup key)
    instrument: str
    units: float
    price: float | None
    realized_pl: float
    reason: str  # TAKE_PROFIT_ORDER | STOP_LOSS_ORDER | TRAILING_STOP_LOSS_ORDER
    time: str


@dataclass
class TradeRecord:
    """One executed order, kept as local history.

    The broker only shows live positions; this table remembers every execution
    with the strategy that fired it and the exit levels it was given, so past
    trades can be audited per strategy.
    """

    strategy_id: str
    symbol: Symbol
    timeframe: str
    action: str  # opened_long | opened_short | closed
    units: float
    source: str = "manual"  # manual | autotrader
    entry_price: float | None = None
    # Exit fill for a ``closed`` record.  Kept separate from entry_price so a
    # completed trade can be displayed as one auditable operation.
    exit_price: float | None = None
    sl_price: float | None = None
    tp_price: float | None = None
    trailing_distance: float | None = None
    realized_pl: float | None = None
    order_id: str = ""
    filled: bool = False
    detail: str | None = None
    signal_time: str | None = None
    # Broker trade id of the position opened here — lets a later broker-side
    # close (TP/SL/trailing) be matched back to this strategy.
    broker_trade_id: str | None = None
    params: dict[str, float | int | bool | str] = field(default_factory=dict)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    executed_at: datetime | None = None


@dataclass
class TradingState:
    enabled: bool = False
    updated_at: datetime | None = None


class TradingDisabledError(RuntimeError):
    """Raised when an execution is attempted while the kill switch is off."""


class LiveConfirmationError(ValueError):
    """Raised when enabling live trading without the typed confirmation."""


@dataclass(frozen=True, kw_only=True)
class OrderExecuted(DomainEvent):
    execution_id: uuid.UUID = field(default_factory=uuid.uuid4)
    symbol: Symbol
    action: str
    units: float
    strategy_id: str
