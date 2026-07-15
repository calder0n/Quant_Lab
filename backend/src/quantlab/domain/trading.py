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
