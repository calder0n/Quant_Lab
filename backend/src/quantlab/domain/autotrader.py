"""Automated-trading assignments.

An ``AutoTrader`` is a saved instruction: run one strategy (with its tuned
parameters) on one symbol/timeframe, sizing each entry at ``units``. A dedicated
worker polls OANDA on the timeframe's cadence and acts on the latest closed bar
through the normal execution path. It only trades while both this assignment is
enabled *and* the global kill switch is on.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from quantlab.domain.market import Symbol, Timeframe
from quantlab.strategies.base import ParamValue


@dataclass
class AutoTrader:
    strategy_id: str
    symbol: Symbol
    timeframe: Timeframe
    units: float
    params: dict[str, ParamValue] = field(default_factory=dict)
    # Trained classification model to gate entries on when the strategy's
    # ``use_ml_filter`` param is set; ``None`` disables the ML filter.
    ml_model_id: str | None = None
    # Trade the opposite side of every signal (buy→sell, sell→buy). For testing
    # whether a consistently-losing strategy fares better reversed.
    invert: bool = False
    enabled: bool = False
    # Bookkeeping (updated by the worker on each processed bar):
    last_bucket: int | None = None  # timeframe bucket already acted on (dedup per bar)
    last_run: datetime | None = None
    last_signal_time: str | None = None
    last_action: str | None = None
    message: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime | None = None
    updated_at: datetime | None = None
