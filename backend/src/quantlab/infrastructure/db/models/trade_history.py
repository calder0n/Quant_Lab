"""Persistence model for the local history of executed orders."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from quantlab.infrastructure.db.base import Base


class TradeHistoryRecord(Base):
    __tablename__ = "trade_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(5))
    action: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16), default="manual")
    units: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float | None] = mapped_column(Float)
    sl_price: Mapped[float | None] = mapped_column(Float)
    tp_price: Mapped[float | None] = mapped_column(Float)
    trailing_distance: Mapped[float | None] = mapped_column(Float)
    realized_pl: Mapped[float | None] = mapped_column(Float)
    order_id: Mapped[str] = mapped_column(String(32), default="")
    filled: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[str | None] = mapped_column(String)
    signal_time: Mapped[str | None] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
