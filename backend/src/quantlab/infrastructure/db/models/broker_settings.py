"""Persistence model for broker credentials configured via the portal.

Stored in the local PostgreSQL instance. Encryption-at-rest arrives with the
authentication phase; until then this is equivalent to keeping the token in
the local ``.env`` file.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from quantlab.infrastructure.db.base import Base


class BrokerSettingsRecord(Base):
    __tablename__ = "broker_settings"

    broker: Mapped[str] = mapped_column(String(32), primary_key=True)
    api_token: Mapped[str] = mapped_column(String, default="")
    account_id: Mapped[str] = mapped_column(String(64), default="")
    environment: Mapped[str] = mapped_column(String(10), default="practice")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
