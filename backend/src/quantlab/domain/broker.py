"""Broker account credentials."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

BrokerEnvironment = Literal["practice", "live"]

OANDA = "oanda"


@dataclass
class BrokerCredentials:
    """API credentials for one broker account."""

    broker: str = OANDA
    api_token: str = ""
    account_id: str = ""
    environment: BrokerEnvironment = "practice"
    updated_at: datetime | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_token)

    @property
    def token_preview(self) -> str | None:
        """Masked token for display; the full token never leaves the backend."""
        if not self.api_token:
            return None
        suffix = self.api_token[-4:] if len(self.api_token) >= 8 else ""
        return f"····{suffix}"
