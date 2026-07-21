"""Persistence model for automated-trading assignments."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from quantlab.infrastructure.db.base import Base


class AutoTraderRecord(Base):
    __tablename__ = "auto_traders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(5))
    units: Mapped[float] = mapped_column(Float)
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_bucket: Mapped[int | None] = mapped_column(BigInteger)
    last_run: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_signal_time: Mapped[str | None] = mapped_column(String(40))
    last_action: Mapped[str | None] = mapped_column(String(20))
    message: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
