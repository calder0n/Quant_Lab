"""Persistence model for the ML/RL model registry."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from quantlab.infrastructure.db.base import Base


class MlModelRecord(Base):
    __tablename__ = "ml_models"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(5), index=True)
    target: Mapped[str] = mapped_column(String(32))
    algorithm: Mapped[str] = mapped_column(String(32), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(5))
    status: Mapped[str] = mapped_column(String(10), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    artifact_path: Mapped[str | None] = mapped_column(String)
    message: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
